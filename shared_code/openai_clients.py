# INVOICEPROCESSINGAPP/shared_code/openai_clients.py
"""
Module for initializing and providing singleton Azure OpenAI client instances.

This module centralizes the creation of AzureOpenAI clients for different
purposes (e.g., agent LLM, vision LLM). It reads configuration details
(endpoint, API key, deployment name, API version) from environment variables
and ensures that only one instance of each client type is created and reused.
"""
import os
import logging
from openai import AzureOpenAI

AGENT_AZURE_OAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AGENT_AZURE_OAI_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AGENT_AZURE_OAI_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_AGENT_DEPLOYMENT_NAME")
AGENT_AZURE_OAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")

_agent_oai_client = None

def get_agent_oai_client():
    """
    Returns a singleton instance of the AzureOpenAI client configured for the agent LLM.

    Initializes the client on the first call using environment variables:
    - `AZURE_OPENAI_ENDPOINT`
    - `AZURE_OPENAI_API_KEY`
    - `AZURE_OPENAI_AGENT_DEPLOYMENT_NAME`
    - `AZURE_OPENAI_API_VERSION`

    Returns:
        AzureOpenAI | None: The initialized client instance, or None if configuration
                            is missing or initialization fails.
    """
    global _agent_oai_client
    if _agent_oai_client is None:
        if AGENT_AZURE_OAI_ENDPOINT and AGENT_AZURE_OAI_KEY and AGENT_AZURE_OAI_DEPLOYMENT_NAME and AGENT_AZURE_OAI_API_VERSION:
            try:
                _agent_oai_client = AzureOpenAI(
                    azure_endpoint=AGENT_AZURE_OAI_ENDPOINT,
                    api_key=AGENT_AZURE_OAI_KEY,
                    api_version=AGENT_AZURE_OAI_API_VERSION
                )
                logging.info("Agent AzureOpenAI client initialized.")
            except Exception as e:
                logging.error(f"Failed to initialize Agent AzureOpenAI client: {e}", exc_info=True)
                return None
        else:
            logging.error("Agent AzureOpenAI client configuration missing.")
            return None
    return _agent_oai_client

VISION_AZURE_OAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
VISION_AZURE_OAI_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
VISION_AZURE_OAI_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_VISION_DEPLOYMENT_NAME")
VISION_AZURE_OAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")

_vision_oai_client = None

def get_vision_oai_client():
    """
    Returns a singleton instance of the AzureOpenAI client configured for the vision-enabled LLM.

    Initializes the client on the first call using environment variables:
    - `AZURE_OPENAI_ENDPOINT` (can be same as agent)
    - `AZURE_OPENAI_API_KEY` (can be same as agent)
    - `AZURE_OPENAI_VISION_DEPLOYMENT_NAME` (specific to the vision model)
    - `AZURE_OPENAI_API_VERSION` (can be same as agent)

    Returns:
        AzureOpenAI | None: The initialized client instance, or None if configuration
                            is missing or initialization fails.
    """
    global _vision_oai_client
    if _vision_oai_client is None:
        if VISION_AZURE_OAI_ENDPOINT and VISION_AZURE_OAI_KEY and VISION_AZURE_OAI_DEPLOYMENT_NAME and VISION_AZURE_OAI_API_VERSION:
            try:
                _vision_oai_client = AzureOpenAI(
                    azure_endpoint=VISION_AZURE_OAI_ENDPOINT,
                    api_key=VISION_AZURE_OAI_KEY,
                    api_version=VISION_AZURE_OAI_API_VERSION
                )
                logging.info("Vision AzureOpenAI client initialized.")
            except Exception as e:
                logging.error(f"Failed to initialize Vision AzureOpenAI client: {e}", exc_info=True)
                return None
        else:
            logging.error("Vision AzureOpenAI client configuration missing.")
            return None
    return _vision_oai_client