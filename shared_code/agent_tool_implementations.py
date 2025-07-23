# InvoiceProcessingApp/shared_code/agent_tool_implementations.py
"""
Implements the actual Python functions for tools available to the Invoice Agent.

This module contains the executable code for each tool defined in
`agent_tool_definitions.py`. These functions interact with backend services
like Azure AI Search (for invoice, PO, and contract data retrieval) and Azure OpenAI
(for vision-based Q&A on invoice PDFs). They handle client initialization,
parameter processing, API calls, and formatting of results back to the agent.
"""
import os
import json
import logging
import pandas as pd
# from azure.core.credentials import AzureKeyCredential
# from azure.search.documents import SearchClient
import json
import time
# from .blob_service import upload_text_to_blob
# from . import blob_service
# from . import pdf_utils
# from .openai_clients import get_vision_oai_client
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from datetime import datetime, timedelta, date,timezone
# from shared_code.openai_clients import get_agent_oai_client
# from blueprints.invoice_ingestion_bp import get_invoice_by_id
# from shared_code.po_data_service import get_po_data_by_number
# from shared_code.openai_service import chat_complete
from shared_code.database_service import get_sql_connection

import io
import csv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)
import os
import json
import logging
import requests
import base64
from azure.identity import InteractiveBrowserCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.message import Message
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.file_attachment import FileAttachment
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import SendMailPostRequestBody
from fpdf import FPDF
    
def _normalize_expr(expr: str) -> str:
    """Normalize expression for better matching"""
    return f"REPLACE(REPLACE(REPLACE(UPPER(LTRIM(RTRIM({expr}))), ' ', ''), ',', ''), '.', '')"

# [REFACTORED] Centralized SQL rewriting logic into a single helper function.
def _rewrite_sql_for_similarity(sql_query: str) -> str:
    """
    Rewrites a SQL query by replacing the abstract SIMILARITY() function
    with a concrete implementation for SQL Server. This version handles
    both string literals and subqueries as the search term by manually
    parsing the function arguments to correctly handle nested parentheses.
    """
    # A non-greedy regex to find all SIMILARITY() calls.
    # The replacer function will parse the contents manually.
    sim_pat = re.compile(r"SIMILARITY\(.*?\)", re.IGNORECASE | re.DOTALL)

    def _sim_repl_parser(match):
        # Extract the full content within the function's parentheses
        full_match_str = match.group(0)
        content_str = full_match_str[len("SIMILARITY("):-1]

        # Manually parse arguments to correctly handle commas inside subqueries
        paren_level = 0
        split_pos = -1
        for i, char in enumerate(content_str):
            if char == '(':
                paren_level += 1
            elif char == ')':
                paren_level -= 1
            elif char == ',' and paren_level == 0:
                split_pos = i
                break
        
        if split_pos == -1:
            logging.warning(f"Could not parse SIMILARITY arguments in: {full_match_str}")
            return full_match_str

        col = content_str[:split_pos].strip()
        term_sql_expr = content_str[split_pos+1:].strip()

        # For LIKE clauses, construct the search pattern differently
        # for literal strings vs. subqueries.
        like_term_expr = ""
        if term_sql_expr.startswith("'") and term_sql_expr.endswith("'"):
            content = term_sql_expr[1:-1].replace("'", "''")
            like_term_expr = f"'%{content}%'"
        else:
            like_term_expr = "'%' + " + term_sql_expr + " + '%'"

        normalized_like_term_expr = "'%' + " + _normalize_expr(term_sql_expr) + " + '%'"

        similarity_expr = f"""
        (CASE 
            WHEN UPPER({col}) = UPPER({term_sql_expr}) THEN 100
            WHEN UPPER({col}) LIKE UPPER({like_term_expr}) THEN 
                CASE 
                    WHEN CHARINDEX(UPPER({term_sql_expr}), UPPER({col})) = 1 THEN 90
                    WHEN CHARINDEX(UPPER({term_sql_expr}), UPPER({col})) > 0 THEN 
                        85 - (CHARINDEX(UPPER({term_sql_expr}), UPPER({col})) - 1) * 2
                    ELSE 80
                END
            WHEN SOUNDEX({col}) = SOUNDEX({term_sql_expr}) THEN 70
            WHEN {_normalize_expr(col)} = {_normalize_expr(term_sql_expr)} THEN 75
            WHEN {_normalize_expr(col)} LIKE {normalized_like_term_expr} THEN 65
            ELSE 0
        END)"""
        
        return similarity_expr

    # Use re.sub with our robust parser function to replace all occurrences
    return sim_pat.sub(_sim_repl_parser, sql_query)


def execute_sql_query_tool(sql_query: str) -> str:
    """
    Executes a single read-only SELECT query with flexible search capabilities.
    Handles SIMILARITY calls by rewriting them with SQL Server compatible functions.
    """
    if not re.match(r'^\s*select\b', sql_query, re.IGNORECASE):
        return json.dumps({"error": "Only single SELECT queries are allowed."})
    if ';' in sql_query.strip().rstrip(';'):
        return json.dumps({"error": "Multiple statements are not permitted."})

    # [MODIFIED] Call the centralized rewrite function
    final_sql_query = _rewrite_sql_for_similarity(sql_query)

    try:
        conn = get_sql_connection()
        cursor = conn.cursor(as_dict=True)
        logging.info(f"Executing rewritten query: {final_sql_query}")
        cursor.execute(final_sql_query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Handle data type conversions
        for row in rows:
            for k, v in row.items():
                if isinstance(v, Decimal):
                    row[k] = str(v)
                elif isinstance(v, (date, datetime)):
                    row[k] = v.isoformat()

        return json.dumps({"results": rows})
    except Exception as e:
        logging.error(f"SQL execution error for query '{final_sql_query}'", exc_info=True)
        return json.dumps({"error": str(e)})


# Enhanced agent search strategy (This function remains unchanged)
def enhanced_search_strategy(search_term: str, table_name: str, column_name: str) -> str:
    """
    Returns a progressive search strategy that tries multiple approaches
    """
    strategies = []
    
    # Strategy 1: Exact match
    strategies.append(f"""
    SELECT *, 100 as similarity_score 
    FROM {table_name} 
    WHERE UPPER({column_name}) = UPPER('{search_term}')
    """)
    
    # Strategy 2: Contains match
    strategies.append(f"""
    SELECT *, 
           CASE 
               WHEN CHARINDEX(UPPER('{search_term}'), UPPER({column_name})) = 1 THEN 90
               WHEN CHARINDEX(UPPER('{search_term}'), UPPER({column_name})) > 0 THEN 80
               ELSE 0
           END as similarity_score
    FROM {table_name} 
    WHERE UPPER({column_name}) LIKE UPPER('%{search_term}%')
    ORDER BY similarity_score DESC
    """)
    
    # Strategy 3: Soundex match
    strategies.append(f"""
    SELECT *, 70 as similarity_score
    FROM {table_name} 
    WHERE SOUNDEX({column_name}) = SOUNDEX('{search_term}')
    """)
    
    # Strategy 4: Normalized fuzzy match
    strategies.append(f"""
    SELECT *, 65 as similarity_score
    FROM {table_name} 
    WHERE {_normalize_expr(column_name)} LIKE '%' + {_normalize_expr(f"'{search_term}'")} + '%'
    """)
    
    return strategies


def export_sql_query_to_csv_tool(
    sql_query: str,
    expiry_minutes: int = 60
) -> dict:
    """
    Executes a single read-only SELECT, writes the results to CSV,
    uploads it to AzureWebJobsStorage in invoices/sessiondumps/,
    and returns a short-lived SAS URL.

    Rejects non-SELECT or multi-statement queries.
    """
    # 1) Ensure only a single SELECT
    if not re.match(r'^\s*select\b', sql_query, re.IGNORECASE):
        return json.dumps({"error": "Only single SELECT queries are allowed."})
    if ';' in sql_query.strip().rstrip(';'):
        return json.dumps({"error": "Multiple statements or trailing semicolons are not permitted."})

    # [MODIFIED] Call the centralized rewrite function to handle SIMILARITY
    final_sql_query = _rewrite_sql_for_similarity(sql_query)

    # 2) Execute the query
    try:
        conn = get_sql_connection()
        cursor = conn.cursor(as_dict=True)
        logging.info(f"Executing rewritten query for export: {final_sql_query}")
        # [MODIFIED] Use the rewritten query
        cursor.execute(final_sql_query)
        rows = cursor.fetchall()
        cols = [col[0] for col in cursor.description]
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"SQL execution error for query '{final_sql_query}'", exc_info=True)
        return json.dumps({"error": str(e)})

    # 3) Serialize to CSV in-memory
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(cols)
        for row in rows:
            record = []
            for c in cols:
                v = row.get(c)
                if isinstance(v, Decimal):
                    record.append(str(v))
                elif isinstance(v, (date, datetime)):
                    record.append(v.isoformat())
                else:
                    record.append(v)
            writer.writerow(record)
        csv_bytes = output.getvalue().encode('utf-8')
    except Exception as e:
        logging.error("CSV serialization error", exc_info=True)
        return json.dumps({"error": "Failed to serialize CSV: " + str(e)})

    # 4) Upload to Blob Storage
    try:
            conn_str = os.getenv("AzureWebJobsStorage")
            if not conn_str:
                raise ValueError("Missing AzureWebJobsStorage setting")
            bsc = BlobServiceClient.from_connection_string(conn_str)

            container = "invoices"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")            
            filename = f"{timestamp}_query_result.csv"
            blob_path = f"sessiondumps/{filename}"

            blob_client = bsc.get_blob_client(container=container, blob=blob_path)
            blob_client.upload_blob(csv_bytes, overwrite=True)
    except Exception as e:
        logging.error("Blob upload error", exc_info=True)
        return json.dumps({"error": "Failed to upload CSV: " + str(e)})

    # 5) Generate SAS URL
    try:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        account_key = bsc.credential.account_key
        sas_token = generate_blob_sas(
            account_name=bsc.account_name,
            container_name=container,
            blob_name=blob_path,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry
        )
        sas_url = f"{blob_client.url}?{sas_token}"
        return {"csv_url": sas_url, "filename": filename}
    except Exception as e:
        logging.error("SAS generation error", exc_info=True)
        return json.dumps({"error": "Failed to generate SAS URL: " + str(e)})



def send_email_with_attachments_tool(
    api_key: str,
    sender_email: str,
    to_emails: str,
    subject: str,
    body: str,
    attachments_json: str = '[]'
) -> str:
    """
    Sends a plain-text email via Brevo (TransactionalEmailsApi), with optional attachments.
    """
    logging.info(f"Preparing email send to: {to_emails}")

    # 1) Parse & validate recipients
    # This is the section that defines `to_list` and was missing before.
    recipients = [e.strip() for e in to_emails.split(',') if e.strip()]
    if not recipients:
        msg = "No valid recipient addresses provided."
        logging.error(msg)
        return json.dumps({"status": "error", "message": msg})
    to_list = [sib_api_v3_sdk.SendSmtpEmailTo(email=addr) for addr in recipients]

    # 2) Parse attachments JSON once
    try:
        attachments_info = json.loads(attachments_json)
        if not isinstance(attachments_info, list):
            raise ValueError("Expected a list of attachments")
    except Exception as e:
        msg = f"Invalid attachments JSON: {e}"
        logging.error(msg, exc_info=True)
        return json.dumps({"status": "error", "message": msg})

    # 3) Fetch & encode each attachment, skipping failures
    attachments_list = []
    for info in attachments_info:
        url = info.get('url')
        filename = info.get('filename')
        if not url or not filename:
            logging.warning(f"Skipping malformed attachment entry: {info}")
            continue
        try:
            logging.info(f"Downloading attachment: {filename}")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            b64 = base64.b64encode(resp.content).decode('utf-8')
            attachments_list.append(
                sib_api_v3_sdk.SendSmtpEmailAttachment(name=filename, content=b64)
            )
            logging.info(f"Attachment ready: {filename}")
        except Exception as e:
            logging.warning(f"Failed to fetch {filename}: {e}, skipping")

    # 4) Configure Brevo client
    config = sib_api_v3_sdk.Configuration()
    config.api_key['api-key'] = api_key
    client = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(config))
    sender = sib_api_v3_sdk.SendSmtpEmailSender(email=sender_email, name="Invoice Agent")

    # Use text_content to send a plain-text email
    email = sib_api_v3_sdk.SendSmtpEmail(
        to=to_list,
        sender=sender,
        subject=subject,
        text_content=body, # Use this parameter for plain-text emails
        attachment=attachments_list
    )

    # 5) Attempt send with retries for transient errors
    max_retries = 3
    backoff = 1
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.send_transac_email(email)
            logging.info(f"Email sent successfully: message_id={resp.message_id}")
            return json.dumps({
                "status": "success",
                "message": "Email sent successfully.",
                "message_id": resp.message_id
            })
        except ApiException as e:
            status = getattr(e, 'status', None)
            logging.error(f"Brevo API error (status={status}): {e.body or e.reason}")
            if status in (429,) or (500 <= (status or 0) < 600):
                if attempt < max_retries:
                    logging.info(f"Retrying in {backoff} seconds (attempt {attempt}/{max_retries})...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            return json.dumps({"status": "error", "message": e.body or str(e)})
        except Exception as e:
            logging.exception("Unexpected error during email send")
            return json.dumps({"status": "error", "message": str(e)})

    # Fallback message if all retries fail
    return json.dumps({"status": "error", "message": "Unable to send email after retries."})
    
# A custom PDF class to handle footers automatically
class ReportPDF(FPDF):
    def footer(self):
        self.set_y(-15)  # Position 1.5 cm from bottom
        self.set_font("Arial", "I", 8)
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        self.cell(0, 10, f"Generated on: {timestamp}", 0, 0, "L")
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "R")

def generate_verification_report_pdf_tool(
    verification_data_json: str,
    invoice_id: str,
    expiry_minutes: int = 60
) -> dict:
    """
    Generates a robust, section-based PDF report. It does not render tables;
    it expects all content, including lists, to be pre-formatted in the text.
    """
    try:
        report_sections = json.loads(verification_data_json)
        pdf = ReportPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 18)
        pdf.cell(0, 10, f"Verification Report for Invoice: {invoice_id}", 0, 1, "C")
        pdf.ln(10)

        for section in report_sections:
            # Section Title
            pdf.set_font("Arial", "B", 14)
            pdf.set_fill_color(224, 224, 224)
            pdf.cell(0, 10, f"  {section.get('section_title', 'Section')}", 0, 1, "L", fill=True)
            pdf.ln(4)
            
            # --- SIMPLIFIED CONTENT RENDERING ---
            # All complex formatting, like bullet points, is expected to be
            # part of the content string itself, using '\n' for newlines.
            if content := section.get("section_content"):
                pdf.set_font("Arial", "", 11)
                pdf.multi_cell(0, 6, content)
            
            pdf.ln(10) # Space after the section

        pdf_bytes = bytes(pdf.output())

    except Exception as e:
        logging.error("PDF generation error", exc_info=True)
        return {"error": f"Failed to generate PDF: {str(e)}"}
    # 2. Upload PDF to Azure Blob Storage
    try:
        conn_str = os.getenv("AzureWebJobsStorage")
        if not conn_str:
            raise ValueError("AzureWebJobsStorage environment variable not set.")
        blob_service_client = BlobServiceClient.from_connection_string(conn_str)
        container_name = "invoices"
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"Verification_Report_{invoice_id}_{timestamp}.pdf"
        blob_path = f"sessiondumps/{filename}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        blob_client.upload_blob(pdf_bytes, overwrite=True)
    except Exception as e:
        logging.error("Blob upload error", exc_info=True)
        return {"error": f"Failed to upload PDF: {str(e)}"}

    # 3. Generate a short-lived SAS URL
    try:
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_path,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time
        )
        sas_url = f"{blob_client.url}?{sas_token}"
        return {"pdf_url": sas_url, "filename": filename}
    except Exception as e:
        logging.error("SAS URL generation error", exc_info=True)
        return {"error": f"Failed to generate SAS URL: {str(e)}"}