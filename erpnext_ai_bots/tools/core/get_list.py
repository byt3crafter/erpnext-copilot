import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetListTool(BaseTool):
    name = "core.get_list"
    description = "Fetch a list of documents with filters, sorting, and pagination."
    parameters = {
        "doctype": {"type": "string", "description": "The DocType to query"},
        "filters": {
            "type": "object",
            "description": "Filter conditions, e.g. {'status': 'Unpaid'}",
        },
        "fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Fields to return",
        },
        "order_by": {
            "type": "string",
            "description": "Sort order, e.g. 'creation desc'",
        },
        "limit": {
            "type": "integer",
            "description": "Max records to return (default 20, max 100)",
        },
    }
    required_params = ["doctype"]
    action_type = "Read"
    required_ptype = "read"

    def execute(self, doctype, filters=None, fields=None, order_by=None, limit=20, **kwargs):
        frappe.has_permission(doctype, ptype="read", throw=True)
        return frappe.get_all(
            doctype,
            filters=filters or {},
            fields=fields or ["name", "creation", "modified"],
            order_by=order_by or "creation desc",
            limit_page_length=min(int(limit), 100),
        )
