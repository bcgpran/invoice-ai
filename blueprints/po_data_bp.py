"""
Purchase Order (PO) Data Processing Blueprint for Azure Functions

This module defines a blob-triggered Azure Function that processes uploaded
PO spreadsheets (CSV/XLSX), performs schema mapping using an LLM, loads the
data into a SQL table via pymssql/SQLAlchemy, and triggers an Azure AI Search
indexer for PO records.

Includes:
- process_master_po_from_blob: Main PO ingestion function
- run_master_po_indexer: Helper to trigger Azure AI Search PO indexer
"""

import os
import logging
import pandas as pd
import azure.functions as func

from shared_code import openai_service
from shared_code import po_data_service
from shared_code import database_service as db  # uses pymssql under the hood

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexerClient

bp = func.Blueprint()

# Standardized schema used for mapping PO files
TARGET_PO_SCHEMA_WITH_DESCRIPTIONS = {
    "PONumber":                    "Purchase Order Number (e.g., PO-123, Order Ref, PO #)",
    "VendorName":                  "Supplier, Seller, or Vendor Company Name (e.g., Vendor, Supplier Name)",
    "ItemName":                    "Product, Service, or Item Description/Name (e.g., Item Description, Product)",
    "Quantity":                    "Quantity of items ordered or services approved (e.g., Qty, Units)",
    "UnitPrice":                   "Price per single unit of the item (e.g., Cost per Item)",
    "AmountWithoutTax":            "Total amount for the line item before tax (e.g., Subtotal, Net Amount)",
    "TaxPercentage":               "Applicable tax rate as a percentage (e.g., VAT %, GST Rate)",
    "ExpectedTaxAmount":           "Calculated or stated tax amount for the line item (e.g., VAT Amount)",
    "TotalPriceWithTax":           "Total price for the line item including all taxes (e.g., Gross Amount)",
    "OrderDate":                   "The date when the order was placed (e.g., Order Date)"
}


# def run_master_po_indexer() -> bool:
#     """
#     Manually triggers the Azure AI Search indexer for PO records.
#     Returns True if successful.
#     """
#     endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
#     key      = os.getenv("AZURE_SEARCH_ADMIN_KEY1")
#     indexer  = os.getenv("AZURE_SEARCH_MASTER_PO_SQL_INDEXER_NAME")

#     if not all([endpoint, key, indexer]):
#         logging.error("Azure AI Search config missing for Master PO indexer.")
#         return False

#     try:
#         logging.info(f"Running Azure AI Search indexer '{indexer}' for Master PO data.")
#         client = SearchIndexerClient(endpoint=endpoint, credential=AzureKeyCredential(key))
#         client.run_indexer(indexer)
#         logging.info(f"Successfully triggered Master PO indexer '{indexer}'.")
#         return True
#     except Exception as e:
#         logging.error(f"Failed to trigger Master PO indexer '{indexer}': {e}", exc_info=True)
#         return False


@bp.function_name("ProcessMasterPoFromBlob")
@bp.blob_trigger(
    arg_name="poBlob",
    path="%PO_DATA_BLOB_PATH_PATTERN%{filename}",
    connection="BLOB_CONNECTION_STRING"
)
def process_master_po_from_blob(poBlob: func.InputStream):
    """
    Blob-triggered function:
    1. Reads an uploaded PO spreadsheet (CSV/XLSX).
    2. Uses OpenAI to map columns to a standard schema.
    3. Standardizes the DataFrame.
    4. Creates/ensures the SQL table via pymssql.
    5. Loads data via SQLAlchemy+pymssql.
    6. Triggers the Azure AI Search indexer.
    """
    filename = os.path.basename(poBlob.name)
    logging.info(f"--- FN START: process_master_po_from_blob for '{filename}' ---")

    # Skip non-spreadsheets
    if not filename.lower().endswith(('.csv', '.xls', '.xlsx')):
        logging.info(f"Skipping non-PO file: {filename}")
        return

    # Skip empty blobs
    if poBlob.length == 0:
        logging.error(f"PO blob '{filename}' is empty; skipping.")
        return

    success_db_load = False
    conn = None
    try:
        # 1) Read into DataFrame
        data = poBlob.read()
        df_original = po_data_service.read_po_file_to_dataframe(data, filename)
        if df_original is None or df_original.empty:
            logging.error(f"Failed to read or empty DataFrame for '{filename}'.")
            return

        # 2) Get column mappings from OpenAI
        mappings = openai_service.get_column_mappings_from_openai(
            list(df_original.columns),
            TARGET_PO_SCHEMA_WITH_DESCRIPTIONS
        )
        if not mappings or not any(v for v in mappings.values()):
            logging.error(f"OpenAI column mapping failed for '{filename}'.")
            return

        # 3) Standardize DataFrame
        df_standardized = po_data_service.create_standardized_po_dataframe(
            df_original, mappings, list(TARGET_PO_SCHEMA_WITH_DESCRIPTIONS.keys())
        )
        if df_standardized is None or df_standardized.empty:
            logging.error(f"Standardized DataFrame is empty for '{filename}'.")
            return

        # 4) Connect & ensure table exists
        conn = db.get_sql_connection()
        table_name = os.getenv("PO_MASTER_TABLE_NAME", "MasterPOData")
        if not po_data_service.create_po_table_from_dataframe(conn, df_standardized, table_name):
            logging.error(f"Failed ensuring table '{table_name}' for '{filename}'.")
            return

        # 5) Load into SQL (append)
        if po_data_service.load_po_dataframe_to_sql(
            df_standardized,
            table_name,
            if_exists_strategy='append'
        ):
            success_db_load = True
            logging.info(f"Appended PO data from '{filename}' into '{table_name}'.")
        else:
            logging.error(f"Failed to load PO data to '{table_name}' for '{filename}'.")
            return

    except ValueError as ve:
        logging.error(f"ValueError processing '{filename}': {ve}", exc_info=True)
    except Exception as e:
        logging.error(f"Unexpected error processing '{filename}': {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

        # 6) Trigger indexer if DB load succeeded
        # if success_db_load:
        #     logging.info("Triggering Master PO indexer...")
        #     if run_master_po_indexer():
        #         logging.info("Master PO indexer triggered successfully.")
        #     else:
        #         logging.warning("Master PO indexer trigger failed.")
        # else:
        #     logging.error(f"Database load failed for '{filename}'; indexer not triggered.")

        logging.info(f"--- FN END: process_master_po_from_blob for '{filename}' ---")
