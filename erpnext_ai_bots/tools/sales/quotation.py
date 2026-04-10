import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateQuotationTool(BaseTool):
    name = "sales.create_quotation"
    description = (
        "Create a draft Quotation for a customer. "
        "Requires the customer name and at least one line item with item_code, qty, and rate. "
        "Returns the new document name and calculated grand total."
    )
    parameters = {
        "party_name": {
            "type": "string",
            "description": "The Customer name exactly as stored in ERPNext.",
        },
        "items": {
            "type": "array",
            "description": "List of line items to include in the quotation.",
            "items": {
                "type": "object",
                "properties": {
                    "item_code": {
                        "type": "string",
                        "description": "ERPNext Item Code.",
                    },
                    "qty": {
                        "type": "number",
                        "description": "Quantity to quote.",
                    },
                    "rate": {
                        "type": "number",
                        "description": "Unit price for this line item.",
                    },
                },
                "required": ["item_code", "qty", "rate"],
            },
        },
        "company": {
            "type": "string",
            "description": "Company for this quotation. Defaults to the session company.",
        },
        "valid_till": {
            "type": "string",
            "description": "Expiry date for the quotation in YYYY-MM-DD format.",
        },
    }
    required_params = ["party_name", "items"]
    action_type = "Create"
    required_doctype = "Quotation"
    required_ptype = "create"

    def execute(self, party_name, items, company=None, valid_till=None, **kwargs):
        frappe.has_permission("Quotation", ptype="create", throw=True)

        doc_data = {
            "doctype": "Quotation",
            "quotation_to": "Customer",
            "party_name": party_name,
            "company": company or self.company,
            "items": [
                {
                    "item_code": item["item_code"],
                    "qty": item["qty"],
                    "rate": item["rate"],
                }
                for item in items
            ],
        }

        if valid_till:
            doc_data["valid_till"] = valid_till

        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "grand_total": doc.grand_total,
        }
