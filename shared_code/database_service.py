"""
Service module for database interactions, primarily with a SQL database using pymssql.

This module provides functions for:
- Establishing database connections.
- Creating necessary table schemas (Invoices, InvoiceLineItems, Contracts) if they don't exist.
- Inserting invoice header, line item, and contract data.
- Checking if a file has already been processed to prevent duplicate entries.
- Retrieving invoice and line item data structured for AI processing.
- Helper utilities for safe data extraction and type conversion (e.g., Decimal).

Configuration for the SQL database connection uses the following environment variables:
- `SQL_SERVER_NAME`
- `SQL_DATABASE_NAME`
- `SQL_USERNAME`
- `SQL_PASSWORD`
"""

import os
import pymssql
import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import datetime
import json


def get_nested_val(data_dict, keys, default=None):
    """
    Safely retrieves a nested value from a dictionary.

    Args:
        data_dict (dict): The dictionary to search within.
        keys (list): Path of nested keys.
        default: Value to return if any key is missing or value is None.
    """
    current = data_dict
    for key in keys:
        if isinstance(current, dict) and key in current and current[key] is not None:
            current = current[key]
        else:
            return default
    return current


def safe_decimal(value, default=None, precision_places=2):
    """
    Safely converts a value to Decimal, rounded to specified precision.

    Args:
        value: int, float, Decimal, or numeric string.
        default: value to return on conversion failure.
        precision_places: decimal places to quantize to.
    """
    if value is None:
        return default
    try:
        if not isinstance(value, (int, float, Decimal)):
            val_str = str(value).strip()
            if not val_str:
                return default
            dec_value = Decimal(val_str)
        else:
            dec_value = Decimal(value)
        quantizer = Decimal(f'1e-{precision_places}')
        return dec_value.quantize(quantizer, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as e:
        logging.warning(f"Could not convert '{value}' to Decimal: {e}. Using default.")
        return default


def get_sql_connection():
    """
    Establishes and returns a pymssql connection.

    Reads config from env vars: SQL_SERVER_NAME, SQL_DATABASE_NAME, SQL_USERNAME, SQL_PASSWORD.
    """
    server   = os.environ.get("SQL_SERVER_NAME")
    database = os.environ.get("SQL_DATABASE_NAME")
    user     = os.environ.get("SQL_USERNAME")
    password = os.environ.get("SQL_PASSWORD")
    missing  = [name for name, val in [
        ("SQL_SERVER_NAME", server),
        ("SQL_DATABASE_NAME", database),
        ("SQL_USERNAME", user),
        ("SQL_PASSWORD", password)
    ] if not val]
    if missing:
        raise ValueError(f"Missing DB config: {', '.join(missing)}")

    try:
        conn = pymssql.connect(
            server=server,
            user=user,
            password=password,
            database=database,
            port=1433
        )
        logging.info("SQL DB connection successful.")
        return conn
    except pymssql.Error as e:
        logging.error(f"Failed to connect to SQL DB: {e}", exc_info=True)
        raise


def create_tables_if_not_exist(conn):
    """
    Create Invoices and InvoiceLineItems if missing.
    """
    cursor = conn.cursor()
    try:
        invoices_sql = (
            "IF OBJECT_ID('Invoices','U') IS NULL "
            "CREATE TABLE Invoices ("
            "InvoiceRecordID INT IDENTITY(1,1) PRIMARY KEY,"
            "InvoiceID VARCHAR(255), InvoiceDate DATE, PurchaseOrder VARCHAR(255), DueDate DATE,"
            "VendorName VARCHAR(255), VendorTaxID VARCHAR(255), VendorPhoneNumber VARCHAR(50),"
            "CustomerID VARCHAR(255), BillingAddress VARCHAR(MAX), ShippingAddress VARCHAR(MAX),"
            "ShippingAddressRecipient VARCHAR(255), SubTotal DECIMAL(18,2), SubTotalCurrencyCode VARCHAR(3),"
            "TotalTax DECIMAL(18,2), TotalTaxCurrencyCode VARCHAR(3), FreightAmount DECIMAL(18,2),"
            "FreightCurrencyCode VARCHAR(3), DiscountAmount DECIMAL(18,2), DiscountAmountCurrencyCode VARCHAR(3),"
            "InvoiceTotal DECIMAL(18,2), InvoiceTotalCurrencyCode VARCHAR(3), AmountDue DECIMAL(18,2),"
            "PreviousUnpaidBalance DECIMAL(18,2), SourceJsonFileName VARCHAR(500) UNIQUE, ProcessedAt DATETIME DEFAULT GETDATE()"
            ");"
            "IF NOT EXISTS(SELECT * FROM sys.indexes WHERE name='IX_Invoices_InvoiceID_File') "
            "CREATE INDEX IX_Invoices_InvoiceID_File ON Invoices(InvoiceID, SourceJsonFileName);"
        )
        cursor.execute(invoices_sql)

        line_items_sql = (
            "IF OBJECT_ID('InvoiceLineItems','U') IS NULL "
            "CREATE TABLE InvoiceLineItems ("
            "LineItemID INT IDENTITY(1,1) PRIMARY KEY,"
            "InvoiceRecordID INT FOREIGN KEY REFERENCES Invoices(InvoiceRecordID) ON DELETE CASCADE,"
            "InvoiceID VARCHAR(255), PONumber VARCHAR(255), VendorName VARCHAR(255),"
            "ItemName VARCHAR(MAX), Quantity DECIMAL(18,3), UnitPrice DECIMAL(18,2),"
            "AmountWithoutTax DECIMAL(18,2), ExpectedTaxAmount DECIMAL(18,2), TaxPercentage DECIMAL(5,2),"
            "TotalPriceWithTax DECIMAL(18,2)"
            ");"
        )
        cursor.execute(line_items_sql)

        conn.commit()
        logging.info("Ensured database schemas for Invoices and InvoiceLineItems.")
    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error creating tables: {e}", exc_info=True)
        raise
    finally:
        cursor.close()


def check_if_file_processed(conn, source_json_filename: str) -> bool:
    """
    Return True if an invoice from this JSON file has been ingested.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(1) FROM Invoices WHERE SourceJsonFileName=%s;",
            (source_json_filename,)
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()


def insert_invoice_data(conn, invoice_data: dict, source_json_filename: str) -> int:
    """
    Insert header data and return the new InvoiceRecordID.
    If this JSON file was already inserted (unique key violation), 
    fetch and return the existing InvoiceRecordID.
    """
    cols = [
        'InvoiceID', 'InvoiceDate', 'PurchaseOrder', 'DueDate',
        'VendorName', 'VendorTaxID', 'VendorPhoneNumber',
        'CustomerID', 'BillingAddress', 'ShippingAddress',
        'ShippingAddressRecipient', 'SubTotal', 'SubTotalCurrencyCode',
        'TotalTax', 'TotalTaxCurrencyCode', 'FreightAmount',
        'FreightCurrencyCode', 'DiscountAmount', 'DiscountAmountCurrencyCode',
        'InvoiceTotal', 'InvoiceTotalCurrencyCode', 'AmountDue',
        'PreviousUnpaidBalance', 'SourceJsonFileName'
    ]

    vals = [
        invoice_data.get('InvoiceId'),
        invoice_data.get('InvoiceDate'),
        invoice_data.get('PurchaseOrder'),
        invoice_data.get('DueDate'),
        invoice_data.get('VendorName'),
        invoice_data.get('VendorTaxId'),
        invoice_data.get('VendorPhoneNumber'),
        invoice_data.get('CustomerId'),
        invoice_data.get('BillingAddress'),
        invoice_data.get('ShippingAddress'),
        invoice_data.get('ShippingAddressRecipient'),
        safe_decimal(invoice_data.get('SubTotalAmount')),
        invoice_data.get('SubTotalCurrencyCode'),
        safe_decimal(invoice_data.get('TotalTaxAmount')),
        invoice_data.get('TotalTaxCurrencyCode'),
        safe_decimal(invoice_data.get('FreightAmount')),
        invoice_data.get('FreightCurrencyCode'),
        safe_decimal(invoice_data.get('DiscountAmount')),
        invoice_data.get('DiscountAmountCurrencyCode'),
        safe_decimal(invoice_data.get('InvoiceTotalAmount')),
        invoice_data.get('InvoiceTotalCurrencyCode'),
        safe_decimal(invoice_data.get('AmountDueAmount')),
        safe_decimal(invoice_data.get('PreviousUnpaidBalanceAmount')),
        source_json_filename
    ]

    placeholders = ",".join(["%s"] * len(cols))
    columns_sql  = ",".join(cols)
    sql = (
        f"INSERT INTO Invoices ({columns_sql}) "
        f"OUTPUT INSERTED.InvoiceRecordID "
        f"VALUES ({placeholders});"
    )

    cursor = conn.cursor()
    try:
        cursor.execute(sql, tuple(vals))
        new_id = cursor.fetchone()[0]
        conn.commit()
        return new_id

    except pymssql.IntegrityError as e:
        # 2627 = unique‐key violation on SourceJsonFileName
        if e.args[0] == 2627:
            logging.warning(
                f"Duplicate JSON '{source_json_filename}', fetching existing ID."
            )
            cursor.execute(
                "SELECT InvoiceRecordID FROM Invoices WHERE SourceJsonFileName=%s;",
                (source_json_filename,)
            )
            return cursor.fetchone()[0]
        else:
            conn.rollback()
            logging.error(f"Error inserting invoice data: {e}", exc_info=True)
            raise

    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error inserting invoice data: {e}", exc_info=True)
        raise

    finally:
        cursor.close()


def insert_line_items_data(conn, invoice_record_id: int, invoice_id: str,
                           po_number: str, vendor_name: str, line_items: list, source_json_filename: str):
    """
    Insert multiple line items for a given invoice.
    """
    if not line_items:
        return
    cursor = conn.cursor()
    try:
        for item in line_items:
            cursor.execute(
                "INSERT INTO InvoiceLineItems ("
                "InvoiceRecordID, InvoiceID, PONumber, VendorName, ItemName, Quantity,"
                "UnitPrice, AmountWithoutTax, ExpectedTaxAmount, TaxPercentage, TotalPriceWithTax"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",
                (
                    invoice_record_id, invoice_id, po_number, vendor_name,
                    item.get('Description'),
                    safe_decimal(item.get('Quantity'), precision_places=3),
                    safe_decimal(item.get('UnitPriceAmount')),
                    safe_decimal(item.get('AmountBeforeTax')),
                    safe_decimal(item.get('TaxAmount')),
                    safe_decimal(item.get('TaxRate')),
                    safe_decimal(item.get('TotalAmountAfterTax'))
                )
            )
        conn.commit()
    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error inserting line items: {e}", exc_info=True)
        raise
    finally:
        cursor.close()


def get_invoice_and_line_items_as_dict(conn, invoice_record_id: int=None, invoice_id_str: str=None) -> dict | None:
    """
    Fetch invoice header and associated line items.
    """
    cursor = conn.cursor()
    try:
        if not invoice_record_id and invoice_id_str:
            cursor.execute(
                "SELECT TOP 1 InvoiceRecordID FROM Invoices "
                "WHERE InvoiceID=%s ORDER BY ProcessedAt DESC, InvoiceRecordID DESC;",
                (invoice_id_str,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            invoice_record_id = row[0]

        if not invoice_record_id:
            return None

        cursor.execute(
            "SELECT * FROM Invoices WHERE InvoiceRecordID=%s;",
            (invoice_record_id,)
        )
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            return None

        invoice = dict(zip(cols, row))
        for k, v in invoice.items():
            if isinstance(v, Decimal):
                invoice[k] = str(v)
            elif isinstance(v, (datetime.date, datetime.datetime)):
                invoice[k] = v.isoformat()

        cursor.execute(
            "SELECT * FROM InvoiceLineItems WHERE InvoiceRecordID=%s ORDER BY LineItemID;",
            (invoice_record_id,)
        )
        li_cols = [col[0] for col in cursor.description]
        items = [dict(zip(li_cols, r)) for r in cursor.fetchall()]
        for item in items:
            for k, v in item.items():
                if isinstance(v, Decimal):
                    item[k] = str(v)
        invoice['LineItems'] = items

        return invoice
    except pymssql.Error as e:
        logging.error(f"Error fetching invoice details: {e}", exc_info=True)
        return None
    finally:
        cursor.close()


def check_if_table_exists(conn, table_name: str, schema_name: str='dbo') -> bool:
    """
    Check if a table exists in the database.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s;",
            (schema_name, table_name)
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()


def create_contracts_table_if_not_exist(conn):
    """
    Create Contracts table if missing, with FLOAT types for numeric columns.
    """
    cursor = conn.cursor()
    try:
        if check_if_table_exists(conn, 'Contracts'):
            return
        contracts_sql = (
            "IF OBJECT_ID('dbo.Contracts','U') IS NULL CREATE TABLE dbo.Contracts ("
            "id INT IDENTITY(1,1) PRIMARY KEY, _SourceDocumentFileName VARCHAR(500),"
            "_ProcessingTimestampUTC DATETIME2 DEFAULT GETUTCDATE(), SupplierName NVARCHAR(MAX),"
            "BuyerName NVARCHAR(MAX), ContractValidityStartDate DATE, ContractValidityEndDate DATE,"
            "ItemName NVARCHAR(MAX), ItemDescription NVARCHAR(MAX), UnitPrice FLOAT, MaxItem FLOAT,"
            "DeliveryDays INT, DeliveryPenaltyAmount FLOAT, DeliveryPenaltyAmountperDay FLOAT,"
            "DeliveryPenaltyRate FLOAT, DeliveryPenaltyRateperDay FLOAT, MaximumTaxCharge FLOAT,"
            "OtherRuleBreakClausesAmount FLOAT, OtherRuleBreakClausesRate FLOAT, _RawExtractedItemJsonData NVARCHAR(MAX)"
            ");"
        )
        cursor.execute(contracts_sql)
        cursor.execute(
            "CREATE INDEX IX_Contracts_SourceDocumentFileName "
            "ON dbo.Contracts(_SourceDocumentFileName);"
        )
        conn.commit()
    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error creating Contracts table: {e}", exc_info=True)
        raise
    finally:
        cursor.close()


def insert_contract_data(conn, contract_items_list: list[dict], source_document_filename: str, processing_timestamp_utc: str) -> int:
    """
    Insert extracted contract item rows into the Contracts table.
    """
    if not contract_items_list:
        return 0
    cursor = conn.cursor()
    try:
        count = 0
        for item in contract_items_list:
            start_date = None
            if item.get('ContractValidityStartDate'):
                try:
                    start_date = datetime.datetime.strptime(
                        item['ContractValidityStartDate'], '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass
            end_date = None
            if item.get('ContractValidityEndDate'):
                try:
                    end_date = datetime.datetime.strptime(
                        item['ContractValidityEndDate'], '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass

            cursor.execute(
                "INSERT INTO dbo.Contracts ("
                "_SourceDocumentFileName, _ProcessingTimestampUTC, SupplierName, BuyerName,"
                "ContractValidityStartDate, ContractValidityEndDate, ItemName, ItemDescription,"
                "UnitPrice, MaxItem, DeliveryDays, DeliveryPenaltyAmount,"
                "DeliveryPenaltyAmountperDay, DeliveryPenaltyRate, DeliveryPenaltyRateperDay,"
                "MaximumTaxCharge, OtherRuleBreakClausesAmount, OtherRuleBreakClausesRate,"
                "_RawExtractedItemJsonData"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",
                (
                    source_document_filename,
                    processing_timestamp_utc,
                    item.get('SupplierName'),
                    item.get('BuyerName'),
                    start_date,
                    end_date,
                    item.get('ItemName'),
                    item.get('ItemDescription'),
                    safe_decimal(item.get('UnitPrice')),
                    safe_decimal(item.get('MaxItem')),
                    item.get('DeliveryDays'),
                    safe_decimal(item.get('DeliveryPenaltyAmount')),
                    safe_decimal(item.get('DeliveryPenaltyAmountperDay')),
                    safe_decimal(item.get('DeliveryPenaltyRate')),
                    safe_decimal(item.get('DeliveryPenaltyRateperDay')),
                    safe_decimal(item.get('MaximumTaxCharge')),
                    safe_decimal(item.get('OtherRuleBreakClausesAmount')),
                    safe_decimal(item.get('OtherRuleBreakClausesRate')),
                    json.dumps(item)
                )
            )
            count += 1
        conn.commit()
        return count
    except pymssql.Error as e:
        conn.rollback()
        logging.error(f"Error inserting contract data: {e}", exc_info=True)
        raise
    finally:
        cursor.close()
