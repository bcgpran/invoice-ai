# InvoiceProcessingApp/function_app.py

"""
Main application file for the Azure Functions host.

This creates the FunctionApp and registers all of your blueprints:
  - invoice_ingestion_bp        (blob trigger)
  - sql_processor_bp            (blob trigger)
  - search_indexer_bp           (event trigger)
  - po_data_bp                  (blob trigger)
  - contract_processing_bp      (blob trigger)
  - agent_orchestrator_bp       (HTTP trigger: /invoice_agent_chat)
  - tool_functions_bp           (HTTP triggers: one per tool)
  
It also exposes a simple health check endpoint.
"""

import azure.functions as func
import logging

# Blueprint imports
from blueprints.invoice_ingestion_bp       import bp as invoice_ingestion_bp
from blueprints.sql_processor_bp           import bp as sql_processor_bp
# from blueprints.search_indexer_bp          import bp as search_indexer_bp
from blueprints.po_data_bp                 import bp as po_data_bp
from blueprints.contract_processing_bp     import bp as contract_processing_bp
from blueprints.agent_orchestrator_bp      import bp as agent_orchestrator_bp
# from blueprints.tool_functions_bp          import bp as tool_functions_bp

# Create the FunctionApp with Function‐level auth
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Register all of the blueprints
app.register_functions(invoice_ingestion_bp)      # /invoice-ingest blob trigger
app.register_functions(sql_processor_bp)          # /sql-load blob trigger
# app.register_functions(search_indexer_bp)         # /index event trigger
app.register_functions(po_data_bp)                # /po-data blob trigger
app.register_functions(contract_processing_bp)    # /contracts blob trigger
app.register_functions(agent_orchestrator_bp)     # /invoice_agent_chat HTTP
# app.register_functions(tool_functions_bp)         # /<tool_name> HTTP

# A simple anonymous health check endpoint
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Health check pinged.")
    return func.HttpResponse(
        "✅ InvoiceProcessingApp is up and running!",
        status_code=200
    )
