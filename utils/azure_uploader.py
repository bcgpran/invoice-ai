# utils/azure_uploader.py

import os
import logging
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

logger = logging.getLogger(__name__)

def upload_files_to_blob(files: list, container_name: str, folder_path: str) -> tuple[list[str], str | None]:
    """
    Uploads a list of files to a specific folder in an Azure Blob container.
    This function contains NO Streamlit UI elements.

    Returns:
        A tuple containing:
        - A list of successfully uploaded filenames.
        - An error message string if an error occurred, otherwise None.
    """
    connect_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connect_str:
        err_msg = "Azure storage credentials are not configured."
        logger.error(err_msg)
        return [], err_msg

    try:
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        successful_uploads = []
        
        for file in files:
            blob_name = f"{folder_path.strip('/')}/{file.name}"
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            
            # Use getvalue() to read bytes from Streamlit's UploadedFile
            blob_client.upload_blob(file.getvalue(), overwrite=True)
            
            logger.info(f"Successfully uploaded '{file.name}' to '{container_name}/{blob_name}'.")
            successful_uploads.append(file.name)
            
        return successful_uploads, None # <-- Return success (no error message)

    except AzureError as e:
        err_msg = f"An Azure error occurred: {e}"
        logger.error(err_msg)
        return [], err_msg # <-- Return failure with an error message
    except Exception as e:
        err_msg = f"An unexpected error occurred: {e}"
        logger.error(err_msg)
        return [], err_msg # <-- Return failure with an error message