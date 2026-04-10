import frappe
from erpnext_ai_bots.tools.base import BaseTool


class UpdateDocumentTool(BaseTool):
    name = "core.update_document"
    description = "Update fields on an existing document. ALWAYS ask user for confirmation first."
    parameters = {
        "doctype": {"type": "string", "description": "The DocType"},
        "name": {"type": "string", "description": "The document name to update"},
        "values": {
            "type": "object",
            "description": "Fields and values to update",
        },
    }
    required_params = ["doctype", "name", "values"]
    action_type = "Update"
    required_ptype = "write"

    def execute(self, doctype, name, values, **kwargs):
        frappe.has_permission(doctype, doc=name, ptype="write", throw=True)
        doc = frappe.get_doc(doctype, name)
        doc.update(values)
        doc.save()
        return {
            "status": "updated",
            "name": doc.name,
            "doctype": doctype,
            "updated_fields": list(values.keys()),
        }
