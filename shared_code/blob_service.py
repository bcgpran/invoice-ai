# INVOICEPROCESSINGAPP/shared_code/blob_service.py
"""
Service module for interacting with Azure Blob Storage.

This module provides utility functions for common blob storage operations:
- Getting a BlobServiceClient instance.
- Uploading text content to a blob.
- Moving (copying and then deleting) a blob within the same storage account.
- Downloading blob content as bytes.
- Checking if a blob exists.

Configuration for the blob storage connection string is expected via the
`BLOB_CONNECTION_STRING` environment variable. Blob paths are typically
expected in the format 'container_name/path/to/blob.ext'.
"""
import os
import logging
from azure.storage.blob import BlobServiceClient

def get_blob_service_client(connection_string: str = None) -> BlobServiceClient | None:
    """
    Creates and returns an Azure BlobServiceClient.

    Uses the provided `connection_string` or, if None, attempts to retrieve it
    from the `BLOB_CONNECTION_STRING` environment variable.

    Args:
        connection_string (str, optional): The Azure Blob Storage connection string.
                                           Defaults to None.

    Returns:
        BlobServiceClient | None: An initialized BlobServiceClient if successful,
                                  otherwise None.
    """
    if not connection_string:
        connection_string = os.environ.get("BLOB_CONNECTION_STRING")
    if not connection_string:
        logging.error("BLOB_CONNECTION_STRING not configured.")
        return None
    try:
        return BlobServiceClient.from_connection_string(connection_string)
    except Exception as e:
        logging.error(f"Failed to create BlobServiceClient: {e}", exc_info=True)
        return None

def upload_text_to_blob(content: str, blob_full_path: str, connection_string: str = None) -> bool:
    """
    Uploads string content to a specified blob in Azure Blob Storage.

    The content is UTF-8 encoded before uploading. The blob will be overwritten
    if it already exists.

    Args:
        content (str): The string content to upload.
        blob_full_path (str): The full path of the blob, including the container name,
                              e.g., 'mycontainer/reports/report.json'.
        connection_string (str, optional): The Azure Blob Storage connection string.
                                           If None, uses the environment variable.

    Returns:
        bool: True if the upload was successful, False otherwise.
    """
    blob_service_client = get_blob_service_client(connection_string)
    if not blob_service_client:
        return False

    try:
        container_name, *blob_name_parts = blob_full_path.split('/', 1)
        if not blob_name_parts:
            logging.error(f"Invalid blob_full_path for upload: '{blob_full_path}'. Must include container name.")
            return False
        actual_blob_name = blob_name_parts[0]

        blob_client = blob_service_client.get_blob_client(container=container_name, blob=actual_blob_name)
        blob_client.upload_blob(content.encode('utf-8'), overwrite=True)
        logging.info(f"Successfully uploaded text to blob: {blob_full_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to upload text to blob '{blob_full_path}': {e}", exc_info=True)
        return False

def move_blob(source_blob_full_path: str, destination_blob_full_path: str, connection_string: str = None) -> bool:
    """
    Moves a blob from a source path to a destination path within the same Azure Storage account.

    This operation involves copying the source blob to the destination and then
    deleting the source blob. Both source and destination paths should include
    the container name.

    Args:
        source_blob_full_path (str): The full path of the source blob,
                                     e.g., 'mycontainer/incoming/invoice.pdf'.
        destination_blob_full_path (str): The full path for the destination blob,
                                          e.g., 'mycontainer/processed/invoice.pdf'.
        connection_string (str, optional): The Azure Blob Storage connection string.
                                           If None, uses the environment variable.

    Returns:
        bool: True if the move was successful, False otherwise.
    """
    blob_service_client = get_blob_service_client(connection_string)
    if not blob_service_client:
        return False

    try:
        source_container_name, *s_blob_name_parts = source_blob_full_path.split('/', 1)
        dest_container_name, *d_blob_name_parts = destination_blob_full_path.split('/', 1)

        if not s_blob_name_parts or not d_blob_name_parts:
            logging.error(f"Invalid source or destination blob path for move. Source: {source_blob_full_path}, Dest: {destination_blob_full_path}")
            return False

        source_actual_blob_name = s_blob_name_parts[0]
        dest_actual_blob_name = d_blob_name_parts[0]

        source_blob_client = blob_service_client.get_blob_client(container=source_container_name, blob=source_actual_blob_name)
        destination_blob_client = blob_service_client.get_blob_client(container=dest_container_name, blob=dest_actual_blob_name)

        if not source_blob_client.exists():
            logging.warning(f"Source blob for move not found: {source_blob_full_path}")
            return False

        destination_blob_client.start_copy_from_url(source_blob_client.url)
        
        source_blob_client.delete_blob()
        logging.info(f"Successfully moved blob from '{source_blob_full_path}' to '{destination_blob_full_path}'")
        return True
    except Exception as e:
        logging.error(f"Failed to move blob from '{source_blob_full_path}' to '{destination_blob_full_path}': {e}", exc_info=True)
        return False

def download_blob_bytes(full_blob_path: str, connection_string: str = None) -> bytes | None:
    """
    Downloads the content of a blob as bytes.

    Args:
        full_blob_path (str): The full path of the blob to download,
                              e.g., 'mycontainer/data/file.bin'.
        connection_string (str, optional): The Azure Blob Storage connection string.
                                           If None, uses the environment variable.

    Returns:
        bytes | None: The content of the blob as bytes if successful and blob exists,
                      otherwise None.
    """
    blob_service_client = get_blob_service_client(connection_string)
    if not blob_service_client:
        return None
    try:
        container_name, *blob_name_parts = full_blob_path.split('/', 1)
        if not blob_name_parts:
            logging.error(f"Invalid blob_full_path for download: '{full_blob_path}'. Must include container name.")
            return None
        actual_blob_name = blob_name_parts[0]

        blob_client = blob_service_client.get_blob_client(container=container_name, blob=actual_blob_name)
        if blob_client.exists():
            downloader = blob_client.download_blob()
            return downloader.readall()
        else:
            logging.warning(f"Blob not found for download: {full_blob_path}")
            return None
    except Exception as e:
        logging.error(f"Failed to download blob '{full_blob_path}': {e}", exc_info=True)
        return None

def check_blob_exists(full_blob_path: str, connection_string: str = None) -> bool:
    """
    Checks if a blob exists at the specified path.

    Args:
        full_blob_path (str): The full path of the blob to check,
                              e.g., 'mycontainer/archive/doc.txt'.
        connection_string (str, optional): The Azure Blob Storage connection string.
                                           If None, uses the environment variable.

    Returns:
        bool: True if the blob exists, False otherwise or if an error occurs.
    """
    blob_service_client = get_blob_service_client(connection_string)
    if not blob_service_client:
        return False
    try:
        container_name, *blob_name_parts = full_blob_path.split('/', 1)
        if not blob_name_parts: return False
        actual_blob_name = blob_name_parts[0]
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=actual_blob_name)
        return blob_client.exists()
    except Exception as e:
        logging.error(f"Error checking blob existence for '{full_blob_path}': {e}", exc_info=True)
        return False