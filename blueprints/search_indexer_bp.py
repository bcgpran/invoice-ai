# """
# Invoice Search Index Trigger Blueprint

# This module defines a blob-triggered Azure Function that runs an Azure AI Search indexer
# whenever a new final report JSON (representing extracted invoice data) is uploaded
# to Blob Storage. It includes logic to:
# - Avoid concurrent indexer execution
# - Peek error content in JSON blobs
# - Trigger the indexer using Azure SDK

# Includes:
# - trigger_search_indexer_on_final_report: main function for blob-triggered indexing
# """

# import azure.functions as func
# import logging
# import os
# from azure.core.credentials import AzureKeyCredential
# from azure.search.documents.indexes import SearchIndexerClient
# from azure.core.exceptions import ResourceExistsError

# bp = func.Blueprint()

# @bp.blob_trigger(
#     arg_name="reportBlob",
#     path="%FINAL_REPORTS_PATH_PATTERN%{filename}",
#     connection="BLOB_CONNECTION_STRING"
# )
# def trigger_search_indexer_on_final_report(reportBlob: func.InputStream):
#     """
#     Trigger Azure AI Search indexer on new final report blob upload.

#     Trigger:
#         - Blob uploaded to FINAL_REPORTS_PATH_PATTERN

#     Args:
#         reportBlob (func.InputStream): JSON blob containing extracted invoice data

#     Behavior:
#         - Checks whether blob is empty or appears to be an error report
#         - Verifies that the indexer is not already running
#         - If safe, triggers the Azure AI Search indexer using the SDK
#         - Logs all outcomes (success, conflict, or failures)

#     Note:
#         - Expects environment variables: AZURE_SEARCH_SERVICE_ENDPOINT,
#           AZURE_SEARCH_ADMIN_KEY, AZURE_SEARCH_INDEXER_NAME
#     """
#     triggering_filename = reportBlob.name 
#     final_reports_prefix = os.environ.get("FINAL_REPORTS_PATH_PATTERN", "invoices/finalreports/").rstrip('/')
#     full_triggering_blob_path_for_log = f"{final_reports_prefix}/{triggering_filename}"

#     logging.info(f"---FN START: trigger_search_indexer_on_final_report for blob: {full_triggering_blob_path_for_log} (raw name: {triggering_filename}) ---")

#     if reportBlob.length == 0:
#         try:
#             content_peek = reportBlob.read(512).decode('utf-8', errors='ignore')
#             reportBlob.seek(0)
#             if '"status": "Failed"' in content_peek.lower() or '"error":' in content_peek.lower():
#                 logging.warning(f"Triggering blob '{full_triggering_blob_path_for_log}' appears to be an error report. Indexer run will be attempted, but check previous step's logs.")
#             else:
#                 logging.warning(f"Triggering blob '{full_triggering_blob_path_for_log}' is empty (but not an error report). Indexer will still run.")
#         except Exception as e_peek:
#             logging.warning(f"Could not peek content of triggering blob '{full_triggering_blob_path_for_log}': {e_peek}. Indexer will still run.")

#     search_service_endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
#     search_admin_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
#     search_indexer_name = os.environ.get("AZURE_SEARCH_INDEXER_NAME")

#     if not all([search_service_endpoint, search_admin_key, search_indexer_name]):
#         logging.error("Azure AI Search configuration missing (endpoint, key, or indexer name). Indexer not run.")
#         return

#     try:
#         credential = AzureKeyCredential(search_admin_key)
#         indexer_client = SearchIndexerClient(endpoint=search_service_endpoint, credential=credential)

#         try:
#             logging.info(f"Checking status for indexer '{search_indexer_name}'...")
#             indexer_status = indexer_client.get_indexer_status(search_indexer_name)
#             if indexer_status and hasattr(indexer_status, 'last_result') and indexer_status.last_result:
#                 current_run_status = indexer_status.last_result.status
#                 logging.info(f"Indexer '{search_indexer_name}' last run status: {current_run_status}")
#                 if current_run_status and current_run_status.lower() == 'inprogress':
#                     logging.warning(f"Indexer '{search_indexer_name}' is already 'inProgress'. Skipping current trigger for '{full_triggering_blob_path_for_log}'.")
#                     return
#             else:
#                 logging.info(f"No last run information found for indexer '{search_indexer_name}', or status is not 'inProgress'. Proceeding to run.")

#         except Exception as e_status:
#             logging.warning(f"Could not reliably get status for indexer '{search_indexer_name}': {e_status}. Proceeding with run attempt.")

#         logging.info(f"Attempting to run Azure AI Search indexer: '{search_indexer_name}' for blob: {full_triggering_blob_path_for_log}")
#         indexer_client.run_indexer(search_indexer_name)
#         logging.info(f"Successfully requested run for Azure AI Search indexer: '{search_indexer_name}' for blob: '{full_triggering_blob_path_for_log}'")

#     except ResourceExistsError as ree:
#         logging.warning(f"Concurrency conflict (409 ResourceExistsError) for indexer '{search_indexer_name}' when processing '{full_triggering_blob_path_for_log}'. Another run was likely in progress or just started. This is usually acceptable. Details: {ree}")
#     except Exception as e:
#         logging.error(f"Failed to trigger Azure AI Search indexer '{search_indexer_name}' for blob '{full_triggering_blob_path_for_log}'. Error: {type(e).__name__} - {e}", exc_info=True)
#     finally:
#         logging.info(f"---FN END: trigger_search_indexer_on_final_report for blob: {full_triggering_blob_path_for_log} ---")
