# InvoiceProcessingApp/shared_code/agent_tool_definitions.py
"""
Defines the structure and schema of tools available to the Invoice Agent LLM.
Now surfaces your SQL tables’ schemas so the agent can write accurate SELECTs.
"""

def get_invoice_agent_tools_definition():
    """
    Returns a list of tool definitions for the Invoice Agent.
    Only one tool here—our read-only SQL executor—augmented with full SQL schema.
    """

    # Invoices table schema (from create_tables_if_not_exist in database_service.py)
    invoices_table_schema_description = """
    Table: Invoices
    - InvoiceRecordID INT IDENTITY(1,1) PRIMARY KEY
    - InvoiceID VARCHAR(255)
    - InvoiceDate DATE
    - PurchaseOrder VARCHAR(255)
    - DueDate DATE
    - VendorName VARCHAR(255)
    - VendorTaxID VARCHAR(255)
    - VendorPhoneNumber VARCHAR(50)
    - CustomerID VARCHAR(255)
    - BillingAddress VARCHAR(MAX)
    - ShippingAddress VARCHAR(MAX)
    - ShippingAddressRecipient VARCHAR(255)
    - SubTotal DECIMAL(18,2)
    - SubTotalCurrencyCode VARCHAR(3)
    - TotalTax DECIMAL(18,2)
    - TotalTaxCurrencyCode VARCHAR(3)
    - FreightAmount DECIMAL(18,2)
    - FreightCurrencyCode VARCHAR(3)
    - DiscountAmount DECIMAL(18,2)
    - DiscountAmountCurrencyCode VARCHAR(3)
    - InvoiceTotal DECIMAL(18,2)
    - InvoiceTotalCurrencyCode VARCHAR(3)
    - AmountDue DECIMAL(18,2)
    - PreviousUnpaidBalance DECIMAL(18,2)
    - SourceJsonFileName VARCHAR(500) UNIQUE
    - ProcessedAt DATETIME DEFAULT GETDATE()
    """

    # InvoiceLineItems table schema (from create_tables_if_not_exist in database_service.py)
    invoice_line_items_table_schema_description = """
    Table: InvoiceLineItems
    - LineItemID INT IDENTITY(1,1) PRIMARY KEY
    - InvoiceRecordID INT FOREIGN KEY REFERENCES Invoices(InvoiceRecordID) ON DELETE CASCADE
    - InvoiceID VARCHAR(255)
    - PONumber VARCHAR(255)
    - VendorName VARCHAR(255)
    - ItemName VARCHAR(MAX)
    - Quantity DECIMAL(18,3)
    - UnitPrice DECIMAL(18,2)
    - AmountWithoutTax DECIMAL(18,2)
    - ExpectedTaxAmount DECIMAL(18,2)
    - TaxPercentage DECIMAL(5,2)
    - TotalPriceWithTax DECIMAL(18,2)
    """

    # MasterPOData table schema (from TARGET_PO_SCHEMA_WITH_DESCRIPTIONS in po_data_bp.py)
    master_po_table_schema_description = """
    Table: MasterPOData
    - id INT IDENTITY(1,1) PRIMARY KEY
    - PONumber (e.g. VARCHAR or NVARCHAR)
    - VendorName
    - OrderDate DATE
    - ItemName
    - Quantity
    - UnitPrice
    - AmountWithoutTax
    - TaxPercentage
    - ExpectedTaxAmount
    - TotalPriceWithTax
    """

    # Contracts table schema (from create_contracts_table_if_not_exist in database_service.py)
    contracts_table_schema_description = """
    Table: Contracts
    - id INT IDENTITY(1,1) PRIMARY KEY
    - _SourceDocumentFileName VARCHAR(500)
    - _ProcessingTimestampUTC DATETIME2 DEFAULT GETUTCDATE()
    - SupplierName NVARCHAR(MAX)
    - BuyerName NVARCHAR(MAX)
    - ContractValidityStartDate DATE
    - ContractValidityEndDate DATE
    - ItemName NVARCHAR(MAX)
    - ItemDescription NVARCHAR(MAX)
    - UnitPrice FLOAT
    - MaxItem FLOAT
    - DeliveryDays INT
    - DeliveryPenaltyAmount FLOAT
    - DeliveryPenaltyAmountperDay FLOAT
    - DeliveryPenaltyRate FLOAT
    - DeliveryPenaltyRateperDay FLOAT
    - MaximumTaxCharge FLOAT
    - OtherRuleBreakClausesAmount FLOAT
    - OtherRuleBreakClausesRate FLOAT
    - _RawExtractedItemJsonData NVARCHAR(MAX)
    """

    # Combine them for injection into the tool’s parameter description
    sql_schema_description = (
        f"{invoices_table_schema_description}\n\n"
        f"{invoice_line_items_table_schema_description}\n\n"
        f"{master_po_table_schema_description}\n\n"
        f"{contracts_table_schema_description}"
    )

    return [
        {
            "type": "function",
            "function": {
                "name": "execute_sql_query_tool",
                "description": (
                    "Execute a read-only SELECT query against the configured database. "
                    "Only single SELECT statements are permitted; any other SQL will be rejected. "
                    "You can call:\n"
                    "  SIMILARITY(ColumnName, 'search_term') — returns a 0–100 similarity score.\n"
                    "Filter by adding `WHERE SIMILARITY(...) >= <threshold>` (e.g. 60).\n"
                    "Example usage on your data:\n"
                    "  SELECT Column1, SIMILARITY(Column1, 'YourSearchTerm') AS SimScore\n"
                    "    FROM YourTableName\n"
                    "   WHERE SIMILARITY(Column1, 'YourSearchTerm') >= 60;\n"
                    "Allowed tables & columns (from your schema description):\n"
                    f"{sql_schema_description}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql_query": {
                            "type": "string",
                            "description": (
                                "A single SELECT statement. Use SIMILARITY(column, 'term') "
                                "and a `WHERE ... >= threshold` to perform fuzzy matching on any VARCHAR column."
                            )
                        }
                    },
                    "required": ["sql_query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "export_sql_query_to_csv_tool",
                "description": (
                    "Execute a single read-only SELECT query and export the results as a CSV file. "
                    "The CSV is uploaded to the 'invoices' container under 'sessiondumps/' in the Function's "
                    "AzureWebJobsStorage account. Returns a short-lived SAS URL for downloading the CSV."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql_query": {
                            "type": "string",
                            "description": "A single SELECT statement to execute and export."
                        },
                        "expiry_minutes": {
                            "type": "integer",
                            "description": "How many minutes the generated SAS URL should remain valid. Default is 60."
                        }
                    },
                    "required": ["sql_query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "request_user_email_consent",
                "description": "CRITICAL: Call this function FIRST and ONLY ONCE when a user asks to send an email. This will show the user a preview of the email and ask for their confirmation. The system will then automatically handle the actual sending process after approval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_emails": {"type": "string", "description": "A single string containing one or more comma-separated email addresses. For example: 'recipient1@example.com,recipient2@example.com'"},
                        "subject": {"type": "string", "description": "The proposed subject line of the email."},
                        "body": {"type": "string", "description": "The proposed body content of the email. Use newlines (\\n) for paragraphs."},
                        "attachments_json": {
                            "type": "string",
                            "description": "A JSON string of a list of attachment objects. Each object must have 'url' and 'filename'. IMPORTANT: For emails without attachments, this MUST be an empty list string: '[]'."
                        }
                    },
                    "required": ["to_emails", "subject", "body", "attachments_json"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_email_with_attachments_tool",
                "description": "Sends an email with one or more attachments. This tool is called by the system after user consent is given.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_emails": {
                            "type": "string",
                            "description": "A comma-separated string of recipient email addresses."
                        },
                        "subject": {
                            "type": "string",
                            "description": "The email subject."
                        },
                        "body": {
                            "type": "string",
                            "description": "The email content make sure to use proper text."
                        },
                        "attachments_json": {
                            "type": "string",
                            "description": "A JSON string of a list of attachment objects. Each object must have a 'url' and a 'filename' key. Example: '[{\"url\": \"...\", \"filename\": \"report.csv\"}, {\"url\": \"...\", \"filename\": \"summary.pdf\"}]'"
                        }
                    },
                    "required": ["to_emails", "subject", "body", "attachments_json"]
                }
            }
        }
    ]