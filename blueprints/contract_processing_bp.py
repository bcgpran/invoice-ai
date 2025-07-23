"""
Contract Processing Blueprint for Azure Functions

This module defines a blob-triggered Azure Function that processes uploaded
contract PDFs. It performs the following steps:

- Converts the contract PDF to images and optionally extracts text
- Uses Azure OpenAI to extract structured, itemized data
- Saves contract line items to a SQL table
- Triggers the Azure AI Search indexer for contract data
"""

import azure.functions as func
import logging
import json
import os
import datetime

import pymssql
from shared_code import blob_service, pdf_utils, openai_service, database_service as db

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexerClient

bp = func.Blueprint()


# def run_contracts_itemized_indexer():
#     """
#     Manually triggers the Azure AI Search indexer for contract items.
#     """
#     endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
#     key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
#     indexer_name = os.environ.get("AZURE_SEARCH_CONTRACTS_SQL_INDEXER_NAME")

#     if not all([endpoint, key, indexer_name]):
#         logging.error("Missing Azure AI Search config for Contracts indexer.")
#         return False

#     try:
#         credential = AzureKeyCredential(key)
#         client = SearchIndexerClient(endpoint=endpoint, credential=credential)
#         client.run_indexer(indexer_name)
#         logging.info(f"Triggered Contracts indexer: '{indexer_name}'")
#         return True
#     except Exception as e:
#         logging.error(f"Failed to trigger Contracts indexer '{indexer_name}': {e}", exc_info=True)
#         return False


@bp.blob_trigger(
    arg_name="contractBlob",
    path="%CONTRACTS_BLOB_PATH_PATTERN%{filename}",
    connection="BLOB_CONNECTION_STRING"
)
def process_contract_pdf_with_llm(contractBlob: func.InputStream):
    """
    Processes a contract PDF uploaded to Blob Storage and loads extracted data to SQL and Search.
    """
    filename = os.path.basename(contractBlob.name)
    logging.info(f"---FN START: process_contract_pdf_with_llm for: {filename} ---")

    if contractBlob.length == 0:
        logging.error(f"Contract blob '{filename}' is empty. Skipping.")
        return

    # 1. Read PDF bytes
    try:
        pdf_bytes = contractBlob.read()
        logging.info(f"Read {len(pdf_bytes)} bytes from PDF: {filename}")
    except Exception as e:
        logging.error(f"Error reading PDF '{filename}': {e}", exc_info=True)
        return

    # 2. Convert to images
    images = pdf_utils.convert_pdf_bytes_to_images_base64(pdf_bytes)
    if not images:
        logging.error(f"Failed to convert PDF '{filename}' to images. Skipping.")
        return
    logging.info(f"Converted PDF '{filename}' to {len(images)} images.")

    # 3. Extract text (optional)
    text_content = ""
    try:
        doc = pdf_utils.fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(len(doc)):
            text_content += doc.load_page(i).get_text("text") + "\n--- End of Page ---\n"
        doc.close()
        logging.info(f"Extracted text from '{filename}', len={len(text_content)} chars.")
    except Exception as e:
        logging.warning(f"Text extraction failed for '{filename}': {e}. Proceeding with images only.")

    # 4. LLM extraction
    try:
        json_str = openai_service.extract_contract_data_as_json(
            images_base64=images,
            pdf_text_content=text_content,
            original_filename=filename
        )
    except Exception as e:
        logging.error(f"LLM extraction error for '{filename}': {e}", exc_info=True)
        return

    if not json_str:
        logging.error(f"LLM returned empty output for '{filename}'. Skipping.")
        return
    logging.info(f"Received JSON output from LLM for '{filename}'.")

    # 5. Parse JSON array
    try:
        items = json.loads(json_str)
        if not isinstance(items, list):
            logging.error(f"LLM output for '{filename}' is not a list.")
            return
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for '{filename}': {e}", exc_info=True)
        return

    logging.info(f"Parsed {len(items)} items from LLM for '{filename}'.")

    # 6. Insert into SQL via pymssql
    conn = None
    success = False
    ts = datetime.datetime.utcnow().isoformat() + 'Z'
    try:
        # get_sql_connection now returns a pymssql.Connection
        conn = db.get_sql_connection()
        db.create_contracts_table_if_not_exist(conn)

        inserted_count = db.insert_contract_data(conn, items, filename, ts)
        if inserted_count >= 0:
            logging.info(f"Inserted {inserted_count} items for '{filename}'.")
            success = True
        else:
            logging.error(f"No items inserted for '{filename}'.")
    except pymssql.Error as e:
        logging.error(f"Database error for '{filename}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except Exception as rb:
                logging.error(f"Rollback failed: {rb}")
    except Exception as e:
        logging.error(f"Unexpected error for '{filename}': {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

    # 7. Trigger indexer if successful
    # if success:
    #     logging.info(f"SQL insert complete for '{filename}', triggering indexer.")
    #     if run_contracts_itemized_indexer():
    #         logging.info("Contracts indexer triggered.")
    #     else:
    #         logging.warning("Contracts indexer trigger failed.")
    # else:
    #     logging.warning(f"SQL insert failed for '{filename}'. Indexer not triggered.")

    logging.info(f"---FN END: process_contract_pdf_with_llm for: {filename} ---")
