import frappe
from erpnext_ai_bots.tools.base import BaseTool


class SubmitDocumentTool(BaseTool):
    name = "core.submit_document"
    description = "Submit (finalize) a draft document. ALWAYS ask user for confirmation first."
    parameters = {
        "doctype": {"type": "string", "description": "The DocType"},
        "name": {"type": "string", "description": "The document name to submit"},
    }
    required_params = ["doctype", "name"]
    action_type = "Submit"
    required_ptype = "submit"

    def execute(self, doctype, name, **kwargs):
        frappe.has_permission(doctype, doc=name, ptype="submit", throw=True)
        doc = frappe.get_doc(doctype, name)
        doc.submit()
        return {
            "status": "submitted",
            "name": doc.name,
            "message": f"{doctype} '{doc.name}' has been submitted.",
        }
