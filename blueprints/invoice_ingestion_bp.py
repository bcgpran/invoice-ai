"""
Invoice Ingestion Blueprint for Azure Functions

This module defines a blob-triggered Azure Function that processes uploaded invoice PDFs.
It converts them to images, sends the images to a multimodal LLM to extract structured
invoice data, and stores the result as a JSON "final report" in another blob location.

Includes:
- Function: generate_final_report_from_pdf_via_llm
  - Triggered by new blob in `INCOMING_BLOBS_PATH_PATTERN`
  - Outputs structured invoice report to `FINAL_REPORTS_PATH_PATTERN`
"""

import azure.functions as func
import logging
import os
import json

from shared_code import pdf_utils
from shared_code import openai_service

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

_search_client_invoices = None


bp = func.Blueprint()

@bp.blob_trigger(
    arg_name="inputBlob",
    path="%INCOMING_BLOBS_PATH_PATTERN%{name}",
    connection="BLOB_CONNECTION_STRING"
)
@bp.blob_output(
    arg_name="outputFinalReportBlob",
    path="%FINAL_REPORTS_PATH_PATTERN%{name}.json",
    connection="BLOB_CONNECTION_STRING"
)
def generate_final_report_from_pdf_via_llm(inputBlob: func.InputStream, outputFinalReportBlob: func.Out[str]):
    """
    Processes a newly uploaded invoice PDF and outputs structured data as JSON.

    Trigger:
        - Blob upload to the path defined in INCOMING_BLOBS_PATH_PATTERN

    Args:
        inputBlob (func.InputStream): The uploaded invoice PDF blob
        outputFinalReportBlob (func.Out[str]): The output blob for the generated JSON final report

    Steps:
        1. Validate that the PDF is non-empty
        2. Convert PDF pages into base64-encoded images
        3. Use an OpenAI LLM to extract structured invoice data (header + line items)
        4. Save the LLM response (or error payload) to FINAL_REPORTS_PATH_PATTERN

    If any step fails, a JSON error report is saved in place of the final report.
    """
    original_pdf_filename = os.path.basename(inputBlob.name)
    logging.info(f"---FN START: generate_final_report_from_pdf_via_llm for: {original_pdf_filename} ---")

    error_payload_str = None

    if inputBlob.length == 0:
        logging.error(f"Input PDF blob '{original_pdf_filename}' is empty. Skipping.")
        error_payload_str = json.dumps({"error": "Empty input PDF", "source_pdf": original_pdf_filename, "status": "Failed"})
        outputFinalReportBlob.set(error_payload_str)
        return

    try:
        pdf_bytes = inputBlob.read()
        pdf_images_base64 = pdf_utils.convert_pdf_bytes_to_images_base64(pdf_bytes)

        if not pdf_images_base64:
            logging.error(f"Failed to convert PDF '{original_pdf_filename}' to images. Skipping.")
            error_payload_str = json.dumps({"error": "PDF to image conversion failed", "source_pdf": original_pdf_filename, "status": "Failed"})
            outputFinalReportBlob.set(error_payload_str)
            return

        llm_generated_json_str = openai_service.generate_invoice_data_from_images_llm(
            pdf_images_base64, original_pdf_filename
        )

        if not llm_generated_json_str:
            logging.error(f"LLM failed to generate structured data for '{original_pdf_filename}'. Final report not created with valid data.")
            error_payload_str = json.dumps({"error": "LLM failed to extract data", "source_pdf": original_pdf_filename, "status": "Failed"})
            outputFinalReportBlob.set(error_payload_str)
            return

        outputFinalReportBlob.set(llm_generated_json_str)
        logging.info(f"Successfully generated and saved final report for '{original_pdf_filename}' to final reports path via LLM.")

    except Exception as e:
        logging.error(f"Unexpected error in generate_final_report_from_pdf_via_llm for {original_pdf_filename}: {e}", exc_info=True)
        error_payload_str = json.dumps({"error": f"Unexpected error during LLM report generation: {str(e)}", "source_pdf": original_pdf_filename, "status": "Failed"})
        try:
            outputFinalReportBlob.set(error_payload_str)
        except Exception as e_set:
            logging.error(f"Failed to set error output for outputFinalReportBlob after main exception: {e_set}")
    finally:
        logging.info(f"---FN END: generate_final_report_from_pdf_via_llm for: {original_pdf_filename} ---")



# def _get_search_client_for_invoices() -> SearchClient | None:
#     global _search_client_invoices
#     if _search_client_invoices is None:
#         endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
#         api_key   = os.getenv("AZURE_SEARCH_QUERY_KEY")
#         index     = os.getenv("AZURE_AI_SEARCH_INDEX_NAME_FOR_INVOICES")
#         if not all([endpoint, api_key, index]):
#             logging.error("Missing Azure Search config for invoices.")
#             return None
#         _search_client_invoices = SearchClient(
#             endpoint=endpoint,
#             index_name=index,
#             credential=AzureKeyCredential(api_key)
#         )
#     return _search_client_invoices

# def get_invoice_by_id(invoice_id: str) -> dict | None:
#     """
#     Fetches a single invoice document (including its LineItems) from the AI Search index
#     by InvoiceID. Returns a Python dict or None if not found / on error.
#     """
#     client = _get_search_client_for_invoices()
#     if not client:
#         return None

#     try:
#         # OData filter: exact match on InvoiceID, include nested LineItems
#         results = client.search(
#             search_text="*",
#             filter=f"InvoiceID eq '{invoice_id}'",
#             select=["*", "LineItems/*"],
#             top=1
#         )
#         docs = [d for d in results]
#         if not docs:
#             return None
#         # Azure SDK gives an object with attribute access—convert to dict via JSON round-trip
#         return json.loads(json.dumps(docs[0], default=str))
#     except Exception as e:
#         logging.error(f"Error fetching invoice '{invoice_id}': {e}", exc_info=True)
#         return None
