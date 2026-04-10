import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateDocumentTool(BaseTool):
    name = "core.create_document"
    description = (
        "Create a new document in ERPNext. Returns the doc as draft "
        "(not submitted). User must confirm before submission."
    )
    parameters = {
        "doctype": {"type": "string", "description": "The DocType to create"},
        "values": {
            "type": "object",
            "description": "Field values for the new document",
        },
    }
    required_params = ["doctype", "values"]
    action_type = "Create"
    required_ptype = "create"

    def execute(self, doctype, values, **kwargs):
        frappe.has_permission(doctype, ptype="create", throw=True)
        doc = frappe.get_doc({"doctype": doctype, **values})
        doc.insert()
        return {
            "status": "created",
            "name": doc.name,
            "doctype": doctype,
            "message": f"Draft {doctype} '{doc.name}' created. Ask user to confirm before submitting.",
        }
