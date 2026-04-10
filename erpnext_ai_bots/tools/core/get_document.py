import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetDocumentTool(BaseTool):
    name = "core.get_document"
    description = "Fetch a single document from ERPNext by doctype and name."
    parameters = {
        "doctype": {
            "type": "string",
            "description": "The DocType name, e.g. 'Sales Invoice', 'Customer'",
        },
        "name": {"type": "string", "description": "The document name/ID"},
        "fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific fields to return (empty = all permitted)",
        },
    }
    required_params = ["doctype", "name"]
    action_type = "Read"
    required_ptype = "read"

    def execute(self, doctype, name, fields=None, **kwargs):
        frappe.has_permission(doctype, doc=name, ptype="read", throw=True)
        doc = frappe.get_doc(doctype, name)
        if fields:
            return {f: doc.get(f) for f in fields if doc.get(f) is not None}
        return doc.as_dict()
