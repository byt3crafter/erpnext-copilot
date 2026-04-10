import frappe
from erpnext_ai_bots.tools.base import BaseTool


class FrappeAPITool(BaseTool):
    name = "core.frappe_api"
    description = (
        "Flexible ERPNext query tool. Fetch documents with any combination of "
        "DocType, filters, fields, grouping, and sorting. More flexible than "
        "core_get_list — supports 'like' filters, 'between' date ranges, "
        "'in' lists, and nested filter arrays. "
        "Use this when the specialized tools don't cover your query needs."
    )
    parameters = {
        "doctype": {
            "type": "string",
            "description": "The DocType to query (e.g. 'Sales Invoice', 'Customer').",
        },
        "filters": {
            "type": "object",
            "description": (
                "Filter dict or list of [field, operator, value] triples. "
                "Operators: =, !=, <, >, <=, >=, like, not like, in, not in, between, is. "
                "Example dict: {\"status\": \"Unpaid\", \"company\": \"Acme\"}. "
                "Example list: [[\"grand_total\", \">\", 1000], [\"customer\", \"like\", \"%Corp%\"]]."
            ),
        },
        "or_filters": {
            "type": "object",
            "description": (
                "OR filter conditions. Same format as filters. "
                "Records matching ANY of these conditions are included."
            ),
        },
        "fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Fields to return. Use ['count(name) as count'] for aggregates, "
                "['sum(grand_total) as total'] for sums, etc. "
                "Defaults to ['name', 'creation', 'modified']."
            ),
        },
        "group_by": {
            "type": "string",
            "description": "GROUP BY clause, e.g. 'customer' or 'posting_date'.",
        },
        "order_by": {
            "type": "string",
            "description": "ORDER BY clause, e.g. 'grand_total desc' or 'posting_date asc'.",
        },
        "limit": {
            "type": "integer",
            "description": "Max rows to return (default 20, max 100).",
        },
    }
    required_params = ["doctype"]
    action_type = "Read"
    required_ptype = "read"

    def execute(
        self,
        doctype: str,
        filters=None,
        or_filters=None,
        fields=None,
        group_by: str = None,
        order_by: str = None,
        limit: int = 20,
        **kwargs,
    ) -> dict:
        frappe.has_permission(doctype, ptype="read", throw=True)

        limit = min(int(limit), 100)

        kwargs_extra = {}
        if group_by:
            kwargs_extra["group_by"] = group_by
        if order_by:
            kwargs_extra["order_by"] = order_by

        try:
            rows = frappe.get_all(
                doctype,
                filters=filters or {},
                or_filters=or_filters or {},
                fields=fields or ["name", "creation", "modified"],
                limit_page_length=limit,
                **kwargs_extra,
            )
        except Exception as exc:
            frappe.log_error(
                title="core.frappe_api execution error",
                message=frappe.get_traceback(),
            )
            return {"error": f"Query failed: {type(exc).__name__}: {exc}", "rows": []}

        return {"rows": rows, "count": len(rows)}
