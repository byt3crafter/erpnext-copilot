import frappe
from erpnext_ai_bots.tools.base import BaseTool


VALID_ENTRY_TYPES = [
    "Material Receipt",
    "Material Issue",
    "Material Transfer",
    "Manufacture",
    "Repack",
]


class CreateStockEntryTool(BaseTool):
    name = "stock.create_stock_entry"
    description = (
        "Create a draft Stock Entry document in ERPNext. "
        "Supports Material Receipt, Material Issue, Material Transfer, Manufacture, and Repack. "
        "Each item in the items list must include item_code and qty; "
        "supply s_warehouse (source) and/or t_warehouse (target) as the entry type requires. "
        "Returns the document name and a confirmation status."
    )
    parameters = {
        "stock_entry_type": {
            "type": "string",
            "enum": VALID_ENTRY_TYPES,
            "description": "The purpose of this stock movement.",
        },
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext.",
        },
        "items": {
            "type": "array",
            "description": (
                "List of items to include in the entry. "
                "Each element is an object with: "
                "item_code (str, required), qty (number, required), "
                "s_warehouse (str, optional — source), t_warehouse (str, optional — target)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "item_code": {"type": "string"},
                    "qty": {"type": "number"},
                    "s_warehouse": {"type": "string"},
                    "t_warehouse": {"type": "string"},
                },
                "required": ["item_code", "qty"],
            },
        },
        "posting_date": {
            "type": "string",
            "description": "Posting date in YYYY-MM-DD format. Defaults to today.",
        },
    }
    required_params = ["stock_entry_type", "company", "items"]
    action_type = "Create"
    required_doctype = "Stock Entry"
    required_ptype = "create"

    def execute(self, stock_entry_type, company, items, posting_date=None, **kwargs):
        frappe.has_permission("Stock Entry", ptype="create", throw=True)

        if stock_entry_type not in VALID_ENTRY_TYPES:
            return {
                "status": "error",
                "message": (
                    f"Invalid stock_entry_type '{stock_entry_type}'. "
                    f"Must be one of: {', '.join(VALID_ENTRY_TYPES)}."
                ),
            }

        if not items:
            return {"status": "error", "message": "At least one item is required."}

        doc = frappe.new_doc("Stock Entry")
        doc.stock_entry_type = stock_entry_type
        doc.company = company or self.company
        if posting_date:
            doc.posting_date = posting_date

        for item in items:
            row = {
                "item_code": item["item_code"],
                "qty": item["qty"],
            }
            if item.get("s_warehouse"):
                row["s_warehouse"] = item["s_warehouse"]
            if item.get("t_warehouse"):
                row["t_warehouse"] = item["t_warehouse"]
            doc.append("items", row)

        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "stock_entry_type": doc.stock_entry_type,
            "company": doc.company,
            "posting_date": str(doc.posting_date),
            "total_items": len(doc.items),
        }
