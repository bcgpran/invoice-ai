# # InvoiceProcessingApp/blueprints/tool_functions_bp.py

# import azure.functions as func
# import json
# import logging

# from shared_code.agent_tool_implementations import (
#     search_invoices_tool,
#     search_master_po_data_tool,
#     search_contracts_tool,
#     answer_visual_query_on_invoice_tool,
#     data_field_evaluator_tool,
#     aggregate_data_tool,
#     createreport,
#     delete_invoice_index_entry_tool
# )

# bp = func.Blueprint()

# @bp.function_name(name="search_invoices_tool")
# @bp.route(route="search_invoices_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def search_invoices_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(search_invoices_tool, req)

# @bp.function_name(name="search_master_po_data_tool")
# @bp.route(route="search_master_po_data_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def search_master_po_data_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(search_master_po_data_tool, req)

# @bp.function_name(name="search_contracts_tool")
# @bp.route(route="search_contracts_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def search_contracts_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(search_contracts_tool, req)

# @bp.function_name(name="answer_visual_query_on_invoice_tool")
# @bp.route(route="answer_visual_query_on_invoice_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def answer_visual_query_on_invoice_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(answer_visual_query_on_invoice_tool, req)

# @bp.function_name(name="data_field_evaluator_tool")
# @bp.route(route="data_field_evaluator_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def data_field_evaluator_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(data_field_evaluator_tool, req)

# @bp.function_name(name="aggregate_data_tool")
# @bp.route(route="aggregate_data_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def aggregate_data_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(aggregate_data_tool, req)


# @bp.function_name(name="createreport")
# @bp.route(route="createreport", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def createreport_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(createreport, req)

# @bp.function_name(name="delete_invoice_index_entry_tool")
# @bp.route(route="delete_invoice_index_entry_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def delete_invoice_index_entry_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     return _invoke_tool(delete_invoice_index_entry_tool, req)

# from shared_code.agent_tool_implementations import po_invoice_reconciliation_tool

# @bp.function_name(name="po_invoice_reconciliation_tool")
# @bp.route(route="po_invoice_reconciliation_tool", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# def po_invoice_reconciliation_tool_handler(req: func.HttpRequest) -> func.HttpResponse:
#     """
#     HTTP endpoint for LLM-based PO vs. Invoice reconciliation.
#     Expects JSON body: { "invoice_id": "<invoice_doc_id>" }
#     """
#     return _invoke_tool(po_invoice_reconciliation_tool, req)




# def _invoke_tool(fn, req: func.HttpRequest) -> func.HttpResponse:
#     """
#     Common logic to parse JSON, invoke the given tool function,
#     and return its result as an HttpResponse.
#     """
#     try:
#         args = req.get_json()
#     except ValueError:
#         return func.HttpResponse(
#             json.dumps({"error": "Invalid JSON body."}),
#             status_code=400,
#             mimetype="application/json"
#         )

#     try:
#         result = fn(**args)
#         if not isinstance(result, str):
#             result = json.dumps(result, default=str)
#         return func.HttpResponse(result, status_code=200, mimetype="application/json")

#     except TypeError as e:
#         logging.error(f"Argument error for {fn.__name__}: {e}", exc_info=True)
#         return func.HttpResponse(
#             json.dumps({"error": f"Invalid arguments for {fn.__name__}: {e}"}),
#             status_code=400,
#             mimetype="application/json"
#         )

#     except Exception as e:
#         logging.error(f"Execution error in {fn.__name__}: {e}", exc_info=True)
#         return func.HttpResponse(
#             json.dumps({"error": f"Error executing {fn.__name__}: {e}"}),
#             status_code=500,
#             mimetype="application/json"
#         )


