"""
Invoice Final Report SQL Loader Blueprint

This Azure Function is triggered when a final report JSON blob (representing
structured invoice data extracted by LLM) is uploaded to Blob Storage.

Responsibilities:
- Parse and validate the final report JSON
- Insert invoice header and line items into SQL (Invoices + InvoiceLineItems tables)
- Ensure idempotency by checking previously processed files
- Use pymssql for all database operations
"""

import azure.functions as func
import logging
import json
import os
import pymssql

from shared_code import database_service as db

bp = func.Blueprint()

# Give this function a unique name in host.json / in the runtime
@bp.function_name("LoadFinalReportToSql")
@bp.blob_trigger(
    arg_name="finalReportBlob",
    path="%FINAL_REPORTS_PATH_PATTERN%{report_filename}",
    connection="BLOB_CONNECTION_STRING"
)
def load_final_report_to_sql(finalReportBlob: func.InputStream):
    """
    Processes a final report JSON blob and inserts invoice data into SQL via pymssql.

    Trigger:
        - Blob upload to FINAL_REPORTS_PATH_PATTERN

    Args:
        finalReportBlob (func.InputStream): JSON blob representing extracted invoice data
    """
    filename = os.path.basename(finalReportBlob.name)
    logging.info(f"--- FN START: load_final_report_to_sql for report: {filename} ---")

    if finalReportBlob.length == 0:
        logging.error(f"Blob '{filename}' is empty; skipping.")
        return

    conn = None
    success = False
    raw = None

    try:
        # 1. Read & parse JSON
        raw = finalReportBlob.read().decode('utf-8')
        report_json = json.loads(raw)

        # 2. Validate structure
        if report_json.get("status") == "Failed" or report_json.get("error"):
            logging.error(f"Error report '{filename}': {report_json.get('error', 'Unknown')} -- aborting.")
            return

        invoice_id = report_json.get("InvoiceID")
        items = report_json.get("LineItems")
        if not invoice_id or not isinstance(items, list):
            logging.error(f"Malformed report '{filename}' (missing InvoiceID/LineItems). Data: {raw[:500]}")
            return

        # 3. Connect & ensure tables exist
        conn = db.get_sql_connection()   # should return pymssql.Connection
        db.create_tables_if_not_exist(conn)

        # 4. Prepare header payload
        header = {
            'InvoiceId': invoice_id,
            'InvoiceDate': report_json.get('InvoiceDate'),
            'PurchaseOrder': report_json.get('PurchaseOrder'),
            'DueDate': report_json.get('DueDate'),
            'VendorName': report_json.get('VendorName'),
            'VendorTaxId': report_json.get('VendorTaxID'),
            'VendorPhoneNumber': report_json.get('VendorPhoneNumber'),
            'CustomerId': report_json.get('CustomerID'),
            'BillingAddress': report_json.get('BillingAddress'),
            'ShippingAddress': report_json.get('ShippingAddress'),
            'ShippingAddressRecipient': report_json.get('ShippingAddressRecipient'),
            'SubTotalAmount': db.safe_decimal(report_json.get('SubTotal')),
            'SubTotalCurrencyCode': report_json.get('SubTotalCurrencyCode'),
            'TotalTaxAmount': db.safe_decimal(report_json.get('TotalTax')),
            'TotalTaxCurrencyCode': report_json.get('TotalTaxCurrencyCode'),
            'FreightAmount': db.safe_decimal(report_json.get('FreightAmount')),
            'FreightCurrencyCode': report_json.get('FreightCurrencyCode'),
            'DiscountAmount': db.safe_decimal(report_json.get('DiscountAmount')),
            'DiscountAmountCurrencyCode': report_json.get('DiscountAmountCurrencyCode'),
            'InvoiceTotalAmount': db.safe_decimal(report_json.get('InvoiceTotal')),
            'InvoiceTotalCurrencyCode': report_json.get('InvoiceTotalCurrencyCode'),
            'AmountDueAmount': db.safe_decimal(report_json.get('AmountDue')),
            'PreviousUnpaidBalanceAmount': db.safe_decimal(report_json.get('PreviousUnpaidBalance')),
        }

        # 5. Prepare line items payload
        parsed_items = []
        for li in items:
            parsed_items.append({
                'Description':         li.get('ItemName'),
                'Quantity':            db.safe_decimal(li.get('Quantity'), precision_places=3),
                'UnitPriceAmount':     db.safe_decimal(li.get('UnitPrice')),
                'AmountBeforeTax':     db.safe_decimal(li.get('AmountWithoutTax')),
                'TaxAmount':           db.safe_decimal(li.get('ExpectedTaxAmount')),
                'TaxRate':             db.safe_decimal(li.get('TaxPercentage')),
                'TotalAmountAfterTax': db.safe_decimal(li.get('TotalPriceWithTax')),
            })

        # 6. Idempotency check
        if db.check_if_file_processed(conn, filename):
            logging.warning(f"'{filename}' already processed; skipping inserts.")
            success = True
        else:
            # 7. Insert header & items
            new_id = db.insert_invoice_data(conn, header, filename)
            if new_id:
                db.insert_line_items_data(
                    conn,
                    new_id,
                    header['InvoiceId'],
                    header['PurchaseOrder'],
                    header['VendorName'],
                    parsed_items,
                    filename
                )
                logging.info(f"Inserted invoice '{invoice_id}' from '{filename}' as record {new_id}.")
                success = True
            else:
                logging.error(f"Failed to insert invoice header for '{filename}'.")

    except json.JSONDecodeError as jde:
        logging.error(f"JSON parse error in '{filename}': {jde}. Raw: {raw[:200] if raw else 'N/A'}", exc_info=True)

    except pymssql.Error as db_err:
        logging.error(f"Database error for '{filename}': {db_err}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception:
                logging.error("Rollback failed.", exc_info=True)

    except Exception as ex:
        logging.error(f"Unexpected error for '{filename}': {ex}", exc_info=True)

    finally:
        if conn:
            conn.close()

        if success:
            logging.info(f"--- FN END: Successfully processed '{filename}' ---")
        else:
            logging.error(f"--- FN END: Failed/skipped processing '{filename}' ---")
