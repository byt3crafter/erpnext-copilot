import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreatePurchaseOrderTool(BaseTool):
    name = "purchase.create_purchase_order"
    description = (
        "Create a Purchase Order to order items from a supplier. "
        "Creates a draft — user must review and submit from ERPNext desk."
    )
    parameters = {
        "supplier": {
            "type": "string",
            "description": "Supplier name exactly as stored in ERPNext",
        },
        "items": {
            "type": "array",
            "description": "List of line items to order",
            "items": {
                "type": "object",
                "properties": {
                    "item_code": {
                        "type": "string",
                        "description": "ERPNext Item Code",
                    },
                    "qty": {
                        "type": "number",
                        "description": "Quantity to order",
                    },
                    "rate": {
                        "type": "number",
                        "description": "Unit price (leave 0 to use the last purchase price)",
                    },
                    "schedule_date": {
                        "type": "string",
                        "description": "Required-by date in YYYY-MM-DD format (optional)",
                    },
                },
                "required": ["item_code", "qty"],
            },
        },
        "company": {
            "type": "string",
            "description": "Company name. Defaults to the session company.",
        },
        "schedule_date": {
            "type": "string",
            "description": "Default required-by date for all items in YYYY-MM-DD format",
        },
    }
    required_params = ["supplier", "items"]
    action_type = "Create"
    required_doctype = "Purchase Order"
    required_ptype = "create"

    def execute(self, supplier, items, company=None, schedule_date=None, **kwargs):
        frappe.has_permission("Purchase Order", ptype="create", throw=True)

        if not items:
            frappe.throw("At least one item is required to create a Purchase Order.")

        default_date = schedule_date or frappe.utils.add_days(frappe.utils.today(), 7)

        order_items = []
        for item in items:
            row = {
                "item_code": item["item_code"],
                "qty": item["qty"],
                "schedule_date": item.get("schedule_date") or default_date,
            }
            if item.get("rate"):
                row["rate"] = item["rate"]
            order_items.append(row)

        doc = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "company": company or self.company,
            "schedule_date": default_date,
            "items": order_items,
        })
        doc.set_missing_values()
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "supplier": supplier,
            "grand_total": doc.grand_total,
            "message": (
                f"Draft Purchase Order '{doc.name}' created for supplier '{supplier}' "
                f"— total {doc.grand_total:.2f}. Please review and submit from ERPNext desk."
            ),
        }
