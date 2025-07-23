# InvoiceProcessingApp/sql_orchestrator_bp.py
"""
SQL‑Only Agent Orchestrator Blueprint

This Azure Function exposes a single HTTP endpoint (`/sql_agent_chat`) that lets users converse
with an AI agent focused solely on running read‑only SQL queries via the
`execute_sql_query_tool` (which supports SIMILARITY‑based fuzzy matching).
"""

import azure.functions as func
import logging
import json
import os

# --- Imports for agent and tools ---
from shared_code.openai_clients import get_agent_oai_client
from shared_code.agent_tool_definitions import get_invoice_agent_tools_definition
from shared_code.agent_tool_implementations import (
    execute_sql_query_tool,
    export_sql_query_to_csv_tool,
    send_email_with_attachments_tool,
    generate_verification_report_pdf_tool 
)

bp = func.Blueprint()

@bp.route(route="invoice_agent_chat", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def invoice_agent_chat(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP entry-point for a conversational agent that can query a database
    and send emails with user consent.
    """
    logging.info("Agent Chat HTTP trigger processed a request.")

    # --- Securely load Brevo credentials from environment settings ---
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    brevo_sender_email = os.environ.get("BREVO_SENDER_EMAIL")

    if not brevo_api_key or not brevo_sender_email:
        logging.error("BREVO_API_KEY or BREVO_SENDER_EMAIL is not configured in application settings.")
        return func.HttpResponse(
            json.dumps({"error": "The email service is not configured correctly on the server."}),
            status_code=500,
            mimetype="application/json",
        )

    agent_oai_client = get_agent_oai_client()
    if not agent_oai_client:
        return func.HttpResponse(
            json.dumps({"error": "Agent LLM not configured."}),
            status_code=500,
            mimetype="application/json",
        )

    # -------- Parse request body --------
    try:
        body = req.get_json()
        user_query = body.get("query")
        history = body.get("history", [])
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body."}),
            status_code=400,
            mimetype="application/json",
        )

    if not user_query:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'query' in request body."}),
            status_code=400,
            mimetype="application/json",
        )

    # -------- Build system prompt --------
    system_prompt = """You are **SQL-Pro Agent**, an expert assistant for querying the company’s invoice database and taking action on the results. You think and act in clear, logical, step-by-step fashion.

**--- Core SQL Workflow ---**

**Available SQL Tools:**
- `execute_sql_query_tool(sql_query: string)`: Executes a single, read-only SELECT statement. Supports flexible fuzzy matching with SIMILARITY(ColumnName, 'search_term') syntax.
- `export_sql_query_to_csv_tool(sql_query: string)`: Executes a SELECT and returns a JSON object with a downloadable CSV link: `{"csv_url": "...", "filename": "..."}`.

**SQL Querying Steps:**
1. **Understand Intent:** Identify which tables and columns are needed (Invoices, InvoiceLineItems, MasterPOData, Contracts).
2. **Craft `SELECT`:** Use exact matches first. If no matches, use `SIMILARITY(...) >= 60` for fuzzy matching (which uses multiple SQL Server string functions internally). 
2.5 VERY IMPORTANT: if you cant find any field, you can search for all the distinct items and then pick out the related ones ONLY IF YOU THINK USER MEANT THOSE, you can confirm if you are doubtful, only tell no results when you are sure there isnt anything user meant.
3. **Execute:** Call the appropriate SQL tool.
4. **Interpret & Answer:** Use query results to answer the user. For large datasets, use `LIMIT` in your query to show a preview, and then offer the full file using `export_sql_query_to_csv_tool`. When providing a download link, use the format: `[filename_from_tool](csv_url_from_tool)`.
5. **Generating File**- Unless the user directly asks for file, you need to show them data sample first and then ask them if they need the file

**Invoice-Verification Recipe:**
- **Fetch invoice** by InvoiceID or SourceJsonFileName.
- **Check duplicates** of InvoiceID or SourceJsonFileName.
- **Pull related PO** from `MasterPOData` via PurchaseOrder.
- **Compare line items:** quantity, unit price, and amounts.
- **Locate and validate contract** in `Contracts` table.
- **Assess penalties** and check tax clauses.
- **Generate & Offer PDF Report:** This is a two-step process:
    1.  **Display in Chat:** First, present a summary of your findings directly to the user. **For any tabular data, you MUST display it as a Markdown table in your chat response.** This is for the user's immediate review.
    2.  **Offer and Format for PDF:** After displaying the Markdown tables, ask the user if they want a formal PDF report. If they agree, you must call the `generate_verification_report_pdf_tool`. For this tool call, you will **re-format the data from your tables into the required bullet-point structure.** The PDF tool CANNOT handle tables.
    
    **General Example of the FINAL JSON format required by the PDF tool:**
    ```json
    [
      {
        "section_title": "Data Field Validation",
        "section_content": "Summary:\\nOne data field was found to be inconsistent with the master records.\\n\\nEvidence:\\n- Field 'VendorID': MISMATCH\\n  - Value in Invoice: 'VEN-9001'\\n  - Value in Master Data: 'VEN-9001-US'\\n\\nRecommendation:\\nUpdate the invoice record with the correct VendorID 'VEN-9001-US' before submitting for payment."
      },
      {
        "section_title": "Financial Calculation Verification",
        "section_content": "Summary:\\nAll financial calculations on the invoice are correct and match the PO.\\n\\nEvidence:\\n- Subtotal: 1,500.00 USD\\n- Tax (8%): 120.00 USD\\n- Total Amount: 1,620.00 USD\\n\\nRecommendation:\\nNo action needed. The amounts are verified."
      }
    ]
    ```
**--- Email Workflow ---**

**Available Email Signal Tool:**
- `request_user_email_consent(to_emails, subject, body, attachments_json)`: Use this to get user approval before sending an email.

**Emailing Steps:**
1.  **Acknowledge Request:** When the user asks to email something.
2.  **Gather Details for Draft:**
    -   **To Emails:** Confirm recipients. If not provided, you MUST ask for them.
    -   **Subject:** Create a clear and concise subject line.
    -   **Body:** Compose a well-structured **PLAIN TEXT** email body. Use newlines (`\\n`) for paragraphs and dashes (`-`) for lists. **DO NOT USE ANY HTML TAGS.**
    -   **Attachments:** This is CRITICAL. Only add attachments if the user **explicitly asks for a file** or if you have **just generated a file** (like a CSV or PDF) for them. If the request is for a simple message (like sending a joke or a notification), the `attachments_json` parameter **MUST be an empty list**: `'[]'`.

3.  **Request User Consent:** Call the `request_user_email_consent` tool with the prepared details.

    **Example 1: Email WITH Attachments**
    ```json
    {
      "to_emails": "user@example.com",
      "subject": "Invoice Report",
      "body": "Hi there,\\n\\nPlease find the attached invoice report you requested.",
      "attachments_json": "[{\\"url\\": \\"https://.../report.csv\\", \\"filename\\": \\"invoice_report.csv\\"}]"
    }
    ```

    **Example 2: Email WITHOUT Attachments (e.g., for a simple message)**
    ```json
    {
      "to_emails": "user@example.com",
      "subject": "sample",
      "body": "sample joke",
      "attachments_json": "[]"
    }
    ```


**Guiding Principles:**
- Only `SELECT` statements—no writes.
- Always think in steps.
- Strive for accuracy and transparency in every answer.
- **Present tabular data as Markdown tables in your chat responses.**
- DO NOT DIRECTLY PROVIDE THE FILE UNLESS ASKED TO ALWAYS GIVE SAMPLE FIRST
- whenever using any field with money number related, i want you to add the respective currency code too if possible for better display
"""

    # -------- Conversation context --------
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_query}]

    # -------- Tool list with email tools --------
    tools = get_invoice_agent_tools_definition()
    available_tool_functions = {
        "execute_sql_query_tool": execute_sql_query_tool,
        "export_sql_query_to_csv_tool": export_sql_query_to_csv_tool,
        "send_email_with_attachments_tool": send_email_with_attachments_tool,
        "generate_verification_report_pdf_tool": generate_verification_report_pdf_tool
    }

    # -------- LLM <-> tool loop --------
    max_iter = 14
    for _ in range(max_iter):
        response = agent_oai_client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_AGENT_DEPLOYMENT_NAME"),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )

        assistant_msg = response.choices[0].message
        tool_calls = assistant_msg.tool_calls

        if not tool_calls:
            final_answer = assistant_msg.content or ""
            return func.HttpResponse(json.dumps({"answer": final_answer, "history": history}), mimetype="application/json")

        # Handle consent tool separately
        call = tool_calls[0]
        if call.function.name == "request_user_email_consent":
            try:
                draft_details = json.loads(call.function.arguments)
                return func.HttpResponse(json.dumps({
                        "action_required": "user_consent_email",
                        "draft_details": draft_details,
                        "history": history,
                        "original_query": user_query
                    }), mimetype="application/json")
            except Exception as e:
                logging.error(f"Error processing consent request: {e}", exc_info=True)
                return func.HttpResponse(json.dumps({"error": f"Error processing consent request: {e}"}), status_code=500)

        # Process other tool calls
        messages.append(json.loads(assistant_msg.model_dump_json()))
        for call in tool_calls:
            fn_name = call.function.name
            fn_impl = available_tool_functions.get(fn_name)

            if not fn_impl:
                tool_content = json.dumps({"error": f"Tool '{fn_name}' is not available."})
            else:
                try:
                    args = json.loads(call.function.arguments)

                    # INJECT SECURE CREDENTIALS INTO THE EMAIL TOOL CALL
                    if fn_name == "send_email_with_attachments_tool":
                        args['api_key'] = brevo_api_key
                        args['sender_email'] = brevo_sender_email

                    tool_result = fn_impl(**args)
                    # The CSV tool returns a dict, so we ensure it's a string for the history
                    tool_content = tool_result if isinstance(tool_result, str) else json.dumps(tool_result)
                except Exception as ex:
                    logging.error(f"Tool execution error for {fn_name}", exc_info=True)
                    tool_content = json.dumps({"error": str(ex)})

            messages.append({
                "tool_call_id": call.id,
                "role": "tool",
                "name": fn_name,
                "content": tool_content,
            })

    fallback_message = "The agent could not complete your request within the allowed steps. Please try rephrasing your request."
    return func.HttpResponse(
        json.dumps({"answer": fallback_message, "history": history}),
        status_code=200,
        mimetype="application/json",
    )