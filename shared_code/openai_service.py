# InvoiceProcessingApp/shared_code/openai_service.py
"""
This module provides services for interacting with Azure OpenAI models
for various tasks related to invoice and contract processing. It includes
functions for:
- Mapping columns from source data to a target schema.
- Correcting extracted invoice JSON data using vision capabilities by comparing
  against invoice images.
- Extracting structured data from contract documents (images and text) into a
  JSON array of items.
- Directly generating structured invoice data (header and line items) from
  invoice images using a vision model.
"""
import os
import json
import logging
import time
from openai import AzureOpenAI
import re
from .openai_clients import get_agent_oai_client, AGENT_AZURE_OAI_DEPLOYMENT_NAME
from .openai_clients import get_vision_oai_client

def get_column_mappings_from_openai(actual_headers: list, target_schema_with_descriptions: dict, retries=2) -> dict:
    """
    Uses Azure OpenAI to map actual column headers from a dataset to a target schema.

    Args:
        actual_headers (list): A list of actual column header strings from the dataset.
        target_schema_with_descriptions (dict): A dictionary where keys are target
                                                semantic names and values are their descriptions.
        retries (int, optional): The number of times to retry the OpenAI API call on failure.
                                 Defaults to 2.

    Returns:
        dict: A dictionary where keys are target semantic names and values are the
              mapped actual header names, or None if no match is found or an error occurs.
              Returns a dictionary with all target names mapped to None on complete failure.

    Raises:
        ValueError: If Azure OpenAI configuration is incomplete or client initialization fails.
    """
    azure_oai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_oai_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_oai_column_map_deployment_name = os.environ.get("AZURE_OPENAI_COLUMN_MAP_DEPLOYMENT_NAME")
    azure_oai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")

    if not all([azure_oai_endpoint, azure_oai_key, azure_oai_column_map_deployment_name, azure_oai_api_version]):
        logging.error("Azure OpenAI configuration for Column Mapping Model not fully set.")
        raise ValueError("Azure OpenAI Column Mapping Model configuration not complete.")

    try:
        client = AzureOpenAI(
            azure_endpoint=azure_oai_endpoint,
            api_key=azure_oai_key,
            api_version=azure_oai_api_version
        )
    except Exception as e_client:
        logging.error(f"Failed to initialize AzureOpenAI client for Column Mapping: {e_client}", exc_info=True)
        raise ValueError(f"AzureOpenAI client initialization for Column Mapping failed: {e_client}")

    target_schema_for_prompt = "\n".join([
        f"- Target Semantic Name: \"{name}\", Description: \"{desc}\""
        for name, desc in target_schema_with_descriptions.items()
    ])
    actual_headers_for_prompt = ", ".join([f'"{h}"' for h in actual_headers])

    system_prompt_content = """
You are an expert data mapping assistant. Your task is to map a list of target semantic column names
to a list of actual column headers found in a dataset.
You MUST return your response as a single, valid JSON object.
The keys of the JSON object MUST be the exact "Target Semantic Name" from the provided schema.
The values in the JSON object MUST be either one of the exact strings from the "Actual Headers" list
or the exact string "NO_MATCH_FOUND" if no reasonable match is found.
Prioritize direct or very close matches. Consider the provided "Description" for each target field.
Be reasonably lenient if an exact wording match isn't present but the meaning is clear.
"""
    user_prompt_content = f"""
Here are the actual column headers from the dataset:
--- ACTUAL HEADERS ---
[{actual_headers_for_prompt}]
--- END ACTUAL HEADERS ---

Here is my target schema, with the semantic meaning of each field I am looking for:
--- TARGET SCHEMA ---
{target_schema_for_prompt}
--- END TARGET SCHEMA ---

Provide ONLY the JSON object in your response. Example format:
{{
  "PONumber": "PO #",
  "VendorName": "Supplier Name",
  "ItemName": "NO_MATCH_FOUND"
}}
"""
    logging.info(f"Sending request to Azure OpenAI Column Mapping Deployment '{azure_oai_column_map_deployment_name}'...")
    response_content_str = None
    for attempt in range(retries + 1):
        try:
            chat_completion = client.chat.completions.create(
                model=azure_oai_column_map_deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt_content},
                    {"role": "user", "content": user_prompt_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            response_content_str = chat_completion.choices[0].message.content
            if not response_content_str:
                logging.warning(f"Attempt {attempt + 1}: Column Mapping Model returned empty content.")
                if attempt < retries: time.sleep(2 * (attempt + 1)); continue
                return {name: None for name in target_schema_with_descriptions.keys()}

            mappings = json.loads(response_content_str)
            validated_mappings = {}
            logging.info("--- Column Mapping Model's Raw Suggestions ---")
            for target_name_llm, actual_header_llm in mappings.items():
                logging.info(f"  LLM suggested: '{target_name_llm}' -> '{actual_header_llm}'")
                normalized_target_name_llm = None
                for schema_target_name in target_schema_with_descriptions.keys():
                    if schema_target_name.lower() == target_name_llm.lower():
                        normalized_target_name_llm = schema_target_name; break
                if not normalized_target_name_llm:
                    logging.warning(f"  LLM returned target '{target_name_llm}' not in schema. Skipping.")
                    continue
                if actual_header_llm == "NO_MATCH_FOUND":
                    validated_mappings[normalized_target_name_llm] = None
                elif actual_header_llm in actual_headers:
                    validated_mappings[normalized_target_name_llm] = actual_header_llm
                else:
                    found_case_insensitive = False
                    for original_header in actual_headers:
                        if str(original_header).lower() == str(actual_header_llm).lower():
                            validated_mappings[normalized_target_name_llm] = original_header
                            found_case_insensitive = True
                            logging.info(f"    Info: Case-insensitive match for '{normalized_target_name_llm}': '{original_header}' (LLM said '{actual_header_llm}')")
                            break
                    if not found_case_insensitive:
                        logging.warning(f"    LLM suggested '{actual_header_llm}' for '{normalized_target_name_llm}', not in actual headers. Marking as no match.")
                        validated_mappings[normalized_target_name_llm] = None
            for target_name_key in target_schema_with_descriptions.keys():
                if target_name_key not in validated_mappings:
                    logging.warning(f"  Target schema name '{target_name_key}' missing from LLM's response. Marking as no match.")
                    validated_mappings[target_name_key] = None
            return validated_mappings
        except json.JSONDecodeError as e_json:
            logging.error(f"Attempt {attempt + 1}: Column Mapping Model response not valid JSON. Error: {e_json}")
            if response_content_str: logging.error(f"Response Text (first 500 chars): {response_content_str[:500]}")
        except Exception as e_api:
            logging.error(f"Attempt {attempt + 1}: Error calling Column Mapping Model: {e_api}", exc_info=True)
            if hasattr(e_api, 'status_code'): logging.error(f"API Status Code: {e_api.status_code}")
            if hasattr(e_api, 'response') and e_api.response is not None and hasattr(e_api.response, 'text'):
                logging.error(f"API Response (first 500 chars): {e_api.response.text[:500]}")
        if attempt < retries:
            logging.info(f"Retrying Column Mapping Model call ({attempt + 1}/{retries})...")
            time.sleep(3 * (attempt + 1))
        else:
            logging.error("Max retries for Column Mapping Model. Failed to get mappings.")
            return {name: None for name in target_schema_with_descriptions.keys()}
    return {name: None for name in target_schema_with_descriptions.keys()}

def correct_invoice_json_with_vision(images_base64: list[str], current_json_data_str: str, retries=2) -> str | None:
    """
    Uses an Azure OpenAI vision model to correct invoice JSON data based on provided images.

    Args:
        images_base64 (list[str]): A list of base64 encoded PNG image strings of the invoice pages.
        current_json_data_str (str): A string containing the current JSON data extracted
                                     from the invoice, which needs verification and correction.
        retries (int, optional): The number of times to retry the OpenAI API call on failure.
                                 Defaults to 2.

    Returns:
        str | None: A string containing the corrected JSON data if successful,
                    otherwise None. The output is a JSON string.
    """
    azure_oai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_oai_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_oai_vision_deployment_name = os.environ.get("AZURE_OPENAI_VISION_CORRECTION_DEPLOYMENT_NAME")
    azure_oai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")

    if not all([azure_oai_endpoint, azure_oai_key, azure_oai_vision_deployment_name, azure_oai_api_version]):
        logging.error("Azure OpenAI configuration for Vision Correction Model not fully set.")
        return None

    try:
        client = AzureOpenAI(
            azure_endpoint=azure_oai_endpoint,
            api_key=azure_oai_key,
            api_version=azure_oai_api_version
        )
    except Exception as e_client:
        logging.error(f"Failed to initialize AzureOpenAI client for Vision Correction: {e_client}", exc_info=True)
        return None

    system_prompt_content = """
You are a meticulous AI data verification assistant. Your task is to review the provided invoice images
and the associated JSON data extracted from a database.
Your goal is to correct any discrepancies in the JSON data based *solely* on the visual information present in the images.
Ensure all values, including but not limited to invoice ID, dates, vendor details, customer details, line item descriptions,
quantities, unit prices, tax amounts, tax rates, subtotals, and grand totals, accurately reflect the content of the invoice images.
If a field in the JSON is not visibly confirmed or contradicted by the images, and seems plausible, you may leave it as is.
If a field is clearly wrong or missing based on the images, correct it or add it if appropriate.
You MUST return the entire JSON object, fully corrected. Preserve the original structure and all keys of the JSON,
only modifying the values where necessary. Ensure the output is a single, valid JSON object. Do NOT wrap the JSON in markdown backticks.

You can remove the line items if you think they are not the actual line items based on the images I give you. Do not correct any calculation; just give me the JSON file which truly represents current data.
Remove any line items which aren't actual line items (for example, if freight amount or something else which isn't a line item is passed in the JSON as a line item, REMOVE THAT).
"""
    user_message_content = [
        {"type": "text", "text": "Please review the following invoice images and correct the provided JSON data based on the visual information. Ensure all values accurately reflect the content of the images. Here is the JSON data that needs verification and correction (ensure your response is ONLY the corrected JSON object, without any markdown wrappers):"},
        {"type": "text", "text": current_json_data_str}
    ]
    for img_b64 in images_base64:
        user_message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "auto"}})

    logging.info(f"Sending request with {len(images_base64)} images to Azure OpenAI Vision Correction Deployment '{azure_oai_vision_deployment_name}'.")
    raw_model_response_str = None
    json_to_parse = None
    for attempt in range(retries + 1):
        try:
            chat_completion_params = {
                "model": azure_oai_vision_deployment_name,
                "messages": [{"role": "system", "content": system_prompt_content}, {"role": "user", "content": user_message_content}],
                "temperature": 0.1,
                "max_tokens": 4096
            }
            if azure_oai_api_version >= "2023-12-01-preview":
                try:
                    chat_completion_params["response_format"] = {"type": "json_object"}
                    logging.info("Attempting to use response_format: json_object for vision correction.")
                except Exception as e_rf:
                    logging.warning(f"Could not set response_format for vision correction: {e_rf}")

            chat_completion = client.chat.completions.create(**chat_completion_params)
            raw_model_response_str = chat_completion.choices[0].message.content
            if not raw_model_response_str:
                logging.warning(f"Attempt {attempt + 1}: Vision Correction Model returned empty content.")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            cleaned_response = raw_model_response_str.strip()
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned_response, re.DOTALL | re.IGNORECASE)
            json_to_parse = match.group(1).strip() if match else cleaned_response
            if match: logging.info(f"Stripped markdown from vision model response. Original len: {len(cleaned_response)}, Cleaned len: {len(json_to_parse)}")
            else: logging.info("No markdown detected in vision model response.")

            parsed_json = json.loads(json_to_parse)
            logging.info(f"Attempt {attempt + 1}: Vision Correction Model returned valid JSON.")
            return json.dumps(parsed_json, indent=2)
        except json.JSONDecodeError as e_json:
            logging.error(f"Attempt {attempt + 1}: Failed to parse JSON from Vision Model. Error: {e_json}")
            if raw_model_response_str: logging.error(f"Raw Model Response (first 500 chars): {raw_model_response_str[:500]}")
            if json_to_parse and json_to_parse != raw_model_response_str: logging.error(f"Attempted to parse (first 500 chars): {json_to_parse[:500]}")
        except Exception as e_api:
            logging.error(f"Attempt {attempt + 1}: Error calling Vision Model: {type(e_api).__name__} - {e_api}", exc_info=True)
            if hasattr(e_api, 'status_code'): logging.error(f"API Status Code: {e_api.status_code}")
            if hasattr(e_api, 'response') and e_api.response is not None:
                 try: logging.error(f"API Error details (JSON): {e_api.response.json()}")
                 except json.JSONDecodeError: logging.error(f"API Error details (text, first 500): {e_api.response.text[:500] if hasattr(e_api.response, 'text') else 'N/A'}")
            elif hasattr(e_api, 'message'): logging.error(f"API Error message: {e_api.message}")
        if attempt < retries:
            logging.info(f"Retrying Vision Correction Model call ({attempt + 2}/{retries + 1})...")
            time.sleep(5 * (attempt + 1))
        else:
            logging.error("Max retries for Vision Correction Model. Failed to get corrected JSON.")
            return None
    return None

def extract_contract_data_as_json(images_base64: list[str], pdf_text_content: str, original_filename: str, retries=2) -> str | None:
    """
    Extracts structured data from contract document images and text using an Azure OpenAI vision model.

    The model is prompted to return a JSON object containing a "contract_items" array,
    where each element represents a distinct item, service, or agreement from the contract.

    Args:
        images_base64 (list[str]): A list of base64 encoded PNG image strings of the contract pages.
        pdf_text_content (str): Text content extracted from the PDF, used as supplementary information.
        original_filename (str): The original filename of the contract document, for context.
        retries (int, optional): The number of times to retry the OpenAI API call on failure.
                                 Defaults to 2.

    Returns:
        str | None: A JSON string representing a list of extracted contract items if successful,
                    otherwise None. The root of the JSON string will be an array.
    """
    azure_oai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_oai_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_oai_contract_extraction_deployment_name = os.environ.get("AZURE_OPENAI_CONTRACT_ITEM_EXTRACTION_DEPLOYMENT_NAME",
                                                                  os.environ.get("AZURE_OPENAI_VISION_CORRECTION_DEPLOYMENT_NAME")) # Fallback
    azure_oai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")

    if not all([azure_oai_endpoint, azure_oai_key, azure_oai_contract_extraction_deployment_name, azure_oai_api_version]):
        logging.error("Azure OpenAI configuration for Contract Item Extraction Model not fully set.")
        return None

    try:
        client = AzureOpenAI(
            azure_endpoint=azure_oai_endpoint,
            api_key=azure_oai_key,
            api_version=azure_oai_api_version
        )
    except Exception as e_client:
        logging.error(f"Failed to initialize AzureOpenAI client for Contract Item Extraction: {e_client}", exc_info=True)
        return None

    prompt_for_llm = f"""
You are an expert AI assistant specialized in extracting structured information from contract documents.
Your task is to identify distinct items, services, or specific agreements within the provided contract document (images and text). For EACH such distinct item/service/agreement, you must extract the specified details.

**Your entire response MUST be a single, valid JSON object.**
**This JSON object MUST contain a key named "contract_items".**
**The value of "contract_items" MUST be a JSON array, where each element of the array is a JSON object representing one item/service/agreement.**

If the contract primarily describes a single overarching service or product without clearly distinct line items, the "contract_items" array should contain a single JSON object.
If multiple distinct items/services/agreements are detailed (e.g., different software modules, different service levels, different physical goods with their own terms), the "contract_items" array should contain a separate JSON object for each.

**Important Instructions for Populating Fields within each item object in the "contract_items" array:**

1.  **Document-Level Information:** Fields like `SupplierName`, `BuyerName`, `ContractValidityStartDate`, and `ContractValidityEndDate` are often defined once for the entire contract.
    *   **Identify these common values first from the overall document content.**
    *   **Then, for EACH item/service/agreement object you create in the "contract_items" array, populate these common fields (`SupplierName`, `BuyerName`, `ContractValidityStartDate`, `ContractValidityEndDate`) with the values found at the document level.** Do not leave them as `null` in the item objects if this information is present anywhere in the contract document as an overarching detail.
    *   If, exceptionally, one of these fields (e.g., `ContractValidityEndDate`) differs per item, then extract the item-specific value. Otherwise, use the common document-level value.

2.  **Item-Specific Information:** Fields like `ItemName`, `ItemDescription`, `UnitPrice`, `MaxItem`, `DeliveryDays`, and all penalty/tax fields should be extracted for each specific item/service/agreement they pertain to.

--- FIELDS FOR EACH ITEM/SERVICE/AGREEMENT (within the "contract_items" array) ---
- "SupplierName": "string (The name of the Supplier or Vendor party in the contract. **If stated once for the whole contract, use that value for every item.**)"
- "BuyerName": "string (The name of the Buyer or Client party in the contract. **If stated once for the whole contract, use that value for every item.**)"
- "ContractValidityStartDate": "YYYY-MM-DD (The overall start date of the contract's term. **If stated once for the whole contract, use that value for every item.**)"
- "ContractValidityEndDate": "YYYY-MM-DD (The overall end date of the contract's term, if specified. **If stated once for the whole contract, use that value for every item.**)"
- "ItemName": "string (A concise name for this specific item, product, service, or agreement component. If not explicitly named, derive a suitable, brief name, e.g., 'Software License Module A', 'Service Level Gold', 'Product X Widget')"
- "ItemDescription": "string (A detailed description of this specific item, service, or agreement component. Capture key specifications or scope details relevant to this item.)"
- "UnitPrice": "double (The unit price for this specific item/service, if applicable. Extract as a number.)"
- "MaxItem": "double (The maximum quantity allowed or applicable for this specific item/service, if specified. Extract as a number.)"
- "DeliveryDays": "double (The maximum number of delivery days allowed for this specific item/service, if specified. Extract as a number.)"
- "DeliveryPenaltyAmount": "double (The fixed penalty amount applicable for delayed delivery of this specific item/service, if stated as an absolute amount per incident. Extract as a number.)"
- "DeliveryPenaltyAmountperDay": "double (The penalty amount per day for delayed delivery of this specific item/service, if stated as an absolute amount per day. Extract as a number.)"
- "DeliveryPenaltyRate": "double (The penalty rate (e.g., percentage of item value) applicable for delayed delivery of this specific item/service, if stated as a rate per incident. Extract as a number, e.g., 0.05 for 5%.)"
- "DeliveryPenaltyRateperDay": "double (The penalty rate per day (e.g., percentage of item value per day) for delayed delivery of this specific item/service. Extract as a number, e.g., 0.001 for 0.1% per day.)"
- "MaximumTaxCharge": "double (The maximum tax rate (e.g., percentage) allowed to be charged for this item/service, if specified. Extract as a number, e.g., 18 for 18%.)"
- "OtherRuleBreakClausesAmount": "double (Any other fixed penalty amount (excluding delivery penalties) applicable for rule breaks related to this specific item/service. Extract as a number.)"
- "OtherRuleBreakClausesRate": "double (Any other penalty rate (e.g., percentage, excluding delivery penalties) applicable for rule breaks related to this specific item/service. Extract as a number, e.g., 0.02 for 2%.)"
--- END FIELDS ---

If a field (especially an item-specific one) is not found or not applicable for a specific item, use `null` as its value (the JSON literal null, not the string "null").
Ensure dates are in YYYY-MM-DD format if possible. For rates, provide them as decimal numbers (e.g., 5% as 0.05). For absolute amounts, provide the number.

Example of expected JSON object output format:
{{
  "contract_items": [
    {{
      "SupplierName": "Global Tech Inc.",
      "BuyerName": "Client Corp.",
      "ContractValidityStartDate": "2023-01-01",
      "ContractValidityEndDate": "2023-12-31",
      "ItemName": "Alpha Software License",
      "ItemDescription": "License for Alpha CRM module, up to 50 users.",
      "UnitPrice": 5000.00,
      "MaxItem": 1.0,
      "DeliveryDays": null,
      "DeliveryPenaltyAmount": null,
      "DeliveryPenaltyAmountperDay": null,
      "DeliveryPenaltyRate": 0.02,
      "DeliveryPenaltyRateperDay": null,
      "MaximumTaxCharge": null,
      "OtherRuleBreakClausesAmount": 1000.00,
      "OtherRuleBreakClausesRate": null
    }},
    {{
      "SupplierName": "Global Tech Inc.",
      "BuyerName": "Client Corp.",
      "ContractValidityStartDate": "2023-01-01",
      "ContractValidityEndDate": "2023-12-31",
      "ItemName": "Beta Support Package",
      "ItemDescription": "Gold level support for Alpha and Beta modules, 24/7 response.",
      "UnitPrice": 1200.00,
      "MaxItem": null,
      "DeliveryDays": null,
      "DeliveryPenaltyAmount": null,
      "DeliveryPenaltyAmountperDay": null,
      "DeliveryPenaltyRate": null,
      "DeliveryPenaltyRateperDay": null,
      "MaximumTaxCharge": 18.0,
      "OtherRuleBreakClausesAmount": null,
      "OtherRuleBreakClausesRate": null
    }}
  ]
}}
Do not include any explanatory text, greetings, or markdown backticks (```json ... ```) around the root JSON object.
The contract document being processed is named: '{original_filename}'.
"""

    user_message_content = [
        {"type": "text", "text": "Please analyze the following contract document (images and text content) and extract the information into the specified JSON format. Here is the extracted text from the PDF:"},
        {"type": "text", "text": pdf_text_content if pdf_text_content else "No text content could be extracted from the PDF. Please rely on the images."}
    ]
    for img_b64 in images_base64:
        user_message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "auto"}})

    logging.info(f"Sending request for contract item extraction: {len(images_base64)} images, text to '{azure_oai_contract_extraction_deployment_name}'.")
    raw_model_response_str, json_to_parse = None, None
    target_item_keys = [
        "SupplierName", "BuyerName", "ContractValidityStartDate", "ContractValidityEndDate",
        "ItemName", "ItemDescription", "UnitPrice", "MaxItem", "DeliveryDays",
        "DeliveryPenaltyAmount", "DeliveryPenaltyAmountperDay", "DeliveryPenaltyRate",
        "DeliveryPenaltyRateperDay", "MaximumTaxCharge", "OtherRuleBreakClausesAmount",
        "OtherRuleBreakClausesRate"
    ]

    for attempt in range(retries + 1):
        try:
            chat_completion_params = {
                "model": azure_oai_contract_extraction_deployment_name,
                "messages": [{"role": "system", "content": prompt_for_llm}, {"role": "user", "content": user_message_content}],
                "temperature": 0.0,
                "max_tokens": 4000
            }
            if azure_oai_api_version >= "2023-12-01-preview":
                try:
                    chat_completion_params["response_format"] = {"type": "json_object"}
                    logging.info("Attempting to use response_format: json_object for contract item extraction.")
                except Exception as e_rf:
                    logging.warning(f"Could not set response_format for contract item extraction: {e_rf}")

            chat_completion = client.chat.completions.create(**chat_completion_params)
            raw_model_response_str = chat_completion.choices[0].message.content
            if not raw_model_response_str:
                logging.warning(f"Attempt {attempt + 1}: Contract Item Extraction Model returned empty content.")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            cleaned_response = raw_model_response_str.strip()
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned_response, re.DOTALL | re.IGNORECASE)
            json_to_parse = match.group(1).strip() if match else cleaned_response
            if match: logging.info("Stripped markdown from contract item model response.")
            else: logging.info("No markdown detected in contract item model response.")

            parsed_root_object = json.loads(json_to_parse)

            if not isinstance(parsed_root_object, dict):
                logging.error(f"Attempt {attempt + 1}: Contract Item Extraction Model did not return a root JSON object. Type: {type(parsed_root_object)}")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            contract_items_list_from_llm = parsed_root_object.get("contract_items")

            if contract_items_list_from_llm is None:
                logging.error(f"Attempt {attempt + 1}: Root JSON object from LLM is missing the 'contract_items' key. Response: {json_to_parse[:500]}")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            if not isinstance(contract_items_list_from_llm, list):
                logging.error(f"Attempt {attempt + 1}: The 'contract_items' field from LLM was not a JSON array. Type: {type(contract_items_list_from_llm)}")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            normalized_items_list = []
            if contract_items_list_from_llm:
                for item_dict in contract_items_list_from_llm:
                    if not isinstance(item_dict, dict):
                        logging.warning(f"Skipping non-dictionary item in 'contract_items' list: {item_dict}")
                        continue
                    normalized_item = {key: item_dict.get(key) for key in target_item_keys}
                    normalized_items_list.append(normalized_item)

            logging.info(f"Attempt {attempt + 1}: Contract Item Extraction Model returned a valid structure with {len(normalized_items_list)} items in 'contract_items' array.")
            return json.dumps(normalized_items_list, indent=2)

        except json.JSONDecodeError as e_json:
            logging.error(f"Attempt {attempt + 1}: Failed to parse JSON from Contract Item Model. Error: {e_json}")
            if raw_model_response_str: logging.error(f"Raw Model Response (first 500 chars): {raw_model_response_str[:500]}")
            if json_to_parse and json_to_parse != raw_model_response_str: logging.error(f"Attempted to parse (first 500 chars): {json_to_parse[:500]}")
        except Exception as e_api:
            logging.error(f"Attempt {attempt + 1}: Error calling Contract Item Model: {type(e_api).__name__} - {e_api}", exc_info=True)
            if hasattr(e_api, 'status_code'): logging.error(f"API Status Code: {e_api.status_code}")
            if hasattr(e_api, 'response') and e_api.response is not None:
                 try: logging.error(f"API Error details (JSON): {e_api.response.json()}")
                 except json.JSONDecodeError: logging.error(f"API Error details (text, first 500): {e_api.response.text[:500] if hasattr(e_api.response, 'text') else 'N/A'}")
            elif hasattr(e_api, 'message'): logging.error(f"API Error message: {e_api.message}")
        if attempt < retries:
            logging.info(f"Retrying Contract Item Model call ({attempt + 2}/{retries + 1})...")
            time.sleep(5 * (attempt + 1))
        else:
            logging.error("Max retries for Contract Item Model. Failed to get JSON array.")
            return None
    return None

def generate_invoice_data_from_images_llm(images_base64: list[str], original_filename: str, retries=2) -> str | None:
    """
    Uses an Azure OpenAI vision model to extract structured invoice data directly from images.

    The LLM is prompted to return data in a "final report" like JSON structure,
    including an invoice header and a 'LineItems' array, suitable for direct
    database ingestion.

    Args:
        images_base64 (list[str]): A list of base64 encoded PNG image strings of the invoice pages.
        original_filename (str): The original filename of the invoice PDF, for context and inclusion in the output.
        retries (int, optional): The number of times to retry the OpenAI API call on failure.
                                 Defaults to 2.

    Returns:
        str | None: A JSON string containing the extracted structured invoice data if successful,
                    otherwise None. The JSON structure is designed to be compatible with SQL loading.
    """
    vision_client = get_vision_oai_client()
    if not vision_client:
        logging.error("Vision LLM client is not initialized for invoice data generation.")
        return None

    azure_oai_vision_deployment_name = os.environ.get("AZURE_OPENAI_VISION_DEPLOYMENT_NAME",
                                                      os.environ.get("AZURE_OPENAI_VISION_CORRECTION_DEPLOYMENT_NAME"))
    azure_oai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")


    if not all([azure_oai_vision_deployment_name, azure_oai_api_version]):
        logging.error("Azure OpenAI Vision configuration for extraction model not fully set (deployment/version).")
        return None

    system_prompt_content = f"""
You are an expert AI assistant specialized in extracting structured information from invoice images.
Your task is to analyze the provided invoice page images and extract all relevant header information and all line item details.
You MUST return your response as a single, valid JSON object.
The JSON object should have top-level keys for all invoice header fields.
It MUST also contain a key named "LineItems". The value of "LineItems" MUST be a JSON array.
Each element in the "LineItems" array MUST be a JSON object representing one line item.

Target Header Fields (use these exact key names in your JSON output):
- "InvoiceID": string (e.g., "INV-123")
- "InvoiceDate": string (YYYY-MM-DD format, e.g., "2023-10-26")
- "PurchaseOrder": string (if present, else null)
- "DueDate": string (YYYY-MM-DD format, if present, else null)
- "VendorName": string
- "VendorTaxID": string (if present, else null)
- "VendorPhoneNumber": string (if present, else null)
- "CustomerID": string (if present, else null)
- "BillingAddress": string (full address text)
- "ShippingAddress": string (full address text, if different or present, else null)
- "ShippingAddressRecipient": string (if present, else null)
- "SubTotal": number (numeric value of subtotal, e.g., 100.50)
- "SubTotalCurrencyCode": string (e.g., "USD", "EUR")
- "TotalTax": number (numeric value of total tax, e.g., 20.10)
- "TotalTaxCurrencyCode": string
- "FreightAmount": number (if present, else null)
- "FreightCurrencyCode": string (if applicable, else null)
- "DiscountAmount": number (if present, else null)
- "DiscountAmountCurrencyCode": string (if applicable, else null)
- "InvoiceTotal": number (numeric value of the grand total, e.g., 120.60)
- "InvoiceTotalCurrencyCode": string
- "AmountDue": number (if different from InvoiceTotal, else use InvoiceTotal; e.g., 120.60)
- "PreviousUnpaidBalance": number (if present, else null)
- "SourceFileName" : "Name of the original pdf"

Target LineItem Fields (for each object in the "LineItems" array, use these exact key names):
- "InvoiceID" : string (id of the invoice)
- "PONumber" : string (PONumber from the invoice (same as PurchaseOrder))
- "VendorName" : string (Vendor name from the invoice)
- "ItemName": string (description of the item or service)
- "Quantity": number (e.g., 2, 1.5)
- "UnitPrice": number (e.g., 50.25)
- "AmountWithoutTax": number (line item total before tax, e.g., 100.50)
- "ExpectedTaxAmount": number (tax amount for the line item, e.g., 10.05)
- "TaxPercentage": number (tax rate as a percentage, e.g., 10 for 10%, not 0.10)
- "TotalPriceWithTax": number (line item total including tax, e.g., 110.55)

If a field is not found or not applicable, use `null` as its value (the JSON literal null).
Ensure all numeric values are numbers, not strings with currency symbols. Dates should be in YYYY-MM-DD format.
The invoice document being processed is named: '{original_filename}'.

Example of desired JSON output structure (values are illustrative):
{{
  "InvoiceID": "562759599",
  "InvoiceDate": "2024-05-20",
  "PurchaseOrder": "9200804063",
  "DueDate": "2024-06-19",
  "VendorName": "Merck Life Science Pty Ltd",
  "VendorTaxID": "66 051 627 831",
  "VendorPhoneNumber": "1800 800 097",
  "CustomerID": "50254990",
  "BillingAddress": "LOCKED BAG 51\\nCLAYTON SOUTH VIC 3169\\nAUSTRALIA",
  "ShippingAddress": "679 SPRINGVALE RD\\nMULGRAVE VIC 3170\\nAUSTRALIA",
  "ShippingAddressRecipient": "AGILENT TECH AUSTRALIA (M) P/L\\nATTN: ALEJANDRO AMORIN SANJURJO",
  "SubTotal": 297.82,
  "SubTotalCurrencyCode": "AUD",
  "TotalTax": 36.28,
  "TotalTaxCurrencyCode": "AUD",
  "FreightAmount": 65.00,
  "FreightCurrencyCode": "AUD",
  "DiscountAmount": null,
  "DiscountAmountCurrencyCode": null,
  "InvoiceTotal": 399.10,
  "InvoiceTotalCurrencyCode": "AUD",
  "AmountDue": 399.10,
  "PreviousUnpaidBalance": null,
  "SourceFileName": "X_562759599_siew-chin_S2512478_Doc7_0.pdf",
  "LineItems": [
    {{
      "InvoiceID": "562759599",
      "PONumber": "9200804063",
      "VendorName": "Merck Life Science Pty Ltd",
      "ItemName": "CLS6120P100-12EA\\nCORNING(R) PLAIN FUNNEL, REUSABLE, DIAM&\\n3926.90.9089/US/04417001",
      "Quantity": 1.000,
      "UnitPrice": 35.55,
      "AmountWithoutTax": 35.55,
      "ExpectedTaxAmount": null,
      "TaxPercentage": null,
      "TotalPriceWithTax": null
    }}
  ]
}}
Your response must be ONLY this JSON object. Do not include any other text or markdown.
ALSO DO NOT INCLUDE ANYTHING OTHER THAN CURRENT ITEM (for example if there are any items that will be delivered in future or in other invoice, dont mention them in this) ONLY MENTION CURRENT ITEMS which we are billed for in current invoice.
"""
    user_message_content = [
        {"type": "text", "text": "Please analyze the following invoice images and extract all header and line item data into the specified JSON format."}
    ]
    for img_b64 in images_base64:
        user_message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "auto"}})

    raw_model_response_str = None
    json_to_parse = None
    for attempt in range(retries + 1):
        try:
            chat_completion_params = {
                "model": azure_oai_vision_deployment_name,
                "messages": [{"role": "system", "content": system_prompt_content}, {"role": "user", "content": user_message_content}],
                "temperature": 0.0,
                "max_tokens": 4096
            }
            if azure_oai_api_version >= "2023-12-01-preview":
                 chat_completion_params["response_format"] = {"type": "json_object"}

            chat_completion = vision_client.chat.completions.create(**chat_completion_params)
            raw_model_response_str = chat_completion.choices[0].message.content

            if not raw_model_response_str:
                logging.warning(f"Attempt {attempt + 1}: Vision Model (for extraction) returned empty content for {original_filename}.")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            cleaned_response = raw_model_response_str.strip()
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned_response, re.DOTALL | re.IGNORECASE)
            json_to_parse = match.group(1).strip() if match else cleaned_response
            
            parsed_json = json.loads(json_to_parse) 
            if not isinstance(parsed_json, dict) or "LineItems" not in parsed_json or not isinstance(parsed_json.get("LineItems"), list) or "InvoiceID" not in parsed_json:
                logging.error(f"Attempt {attempt + 1}: LLM output for {original_filename} is not a valid dict or missing critical fields 'InvoiceID' or 'LineItems' array. Content: {json_to_parse[:500]}")
                if attempt < retries: time.sleep(5 * (attempt + 1)); continue
                return None

            logging.info(f"Attempt {attempt + 1}: Vision Model successfully generated structured JSON for {original_filename}.")
            return json_to_parse
            
        except json.JSONDecodeError as e_json:
            logging.error(f"Attempt {attempt + 1}: Failed to parse JSON from Vision Model for {original_filename}. Error: {e_json}. Raw: {raw_model_response_str[:500] if raw_model_response_str else 'N/A'}", exc_info=True)
        except Exception as e_api:
            logging.error(f"Attempt {attempt + 1}: Error calling Vision Model for {original_filename}: {type(e_api).__name__} - {e_api}", exc_info=True)
        if attempt < retries:
            logging.info(f"Retrying Vision Model call for {original_filename} ({attempt + 2}/{retries + 1})...")
            time.sleep(5 * (attempt + 1))
        else:
            logging.error(f"Max retries for Vision Model on {original_filename}. Failed to get structured JSON.")
            return None
    return None



def chat_complete(
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 800
) -> str:
    """
    Wrapper for Azure OpenAI chat completion using the agent deployment.
    Reads:
      - AGENT_AZURE_OAI_DEPLOYMENT_NAME
      - AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION
    """
    client = get_agent_oai_client()
    if not client:
        logging.error("Agent AzureOpenAI client not configured.")
        raise ValueError("Agent LLM client not configured.")

    try:
        resp = client.chat.completions.create(
            model=AGENT_AZURE_OAI_DEPLOYMENT_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return resp.choices[0].message.content
    except Exception as e:
        logging.error(f"chat_complete failed: {e}", exc_info=True)
        raise
    
    