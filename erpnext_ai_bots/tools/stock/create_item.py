import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateItemTool(BaseTool):
    name = "stock.create_item"
    description = (
        "Create a new item/product in ERPNext. "
        "Optionally sets the selling rate and default warehouse. "
        "Checks for a duplicate item_code before creating."
    )
    parameters = {
        "item_code": {
            "type": "string",
            "description": "Unique item code (required). Used as the document ID.",
        },
        "item_name": {
            "type": "string",
            "description": "Display name for the item. Defaults to item_code if omitted.",
        },
        "item_group": {
            "type": "string",
            "description": "Item group. Default: All Item Groups",
        },
        "stock_uom": {
            "type": "string",
            "description": "Unit of measure (e.g. Nos, Kg, Ltr). Default: Nos",
        },
        "is_stock_item": {
            "type": "boolean",
            "description": "Whether to track inventory for this item. Default: true",
        },
        "standard_rate": {
            "type": "number",
            "description": "Standard selling rate (sets item_defaults valuation_rate field)",
        },
        "description": {
            "type": "string",
            "description": "Long description of the item",
        },
        "default_warehouse": {
            "type": "string",
            "description": "Default warehouse for this item",
        },
    }
    required_params = ["item_code"]
    action_type = "Create"
    required_ptype = "create"
    required_doctype = "Item"

    def execute(
        self,
        item_code,
        item_name=None,
        item_group=None,
        stock_uom=None,
        is_stock_item=True,
        standard_rate=None,
        description=None,
        default_warehouse=None,
        **kwargs,
    ):
        frappe.has_permission("Item", ptype="create", throw=True)

        # ── Duplicate check ───────────────────────────────────────────────────
        if frappe.db.exists("Item", item_code):
            existing_doc = frappe.get_doc("Item", item_code)
            return {
                "created": False,
                "warning": "duplicate",
                "message": (
                    f"An item with code '{item_code}' already exists "
                    f"('{existing_doc.item_name}'). "
                    f"Use a different item_code or look up the existing item."
                ),
                "existing_item": {
                    "item_code": existing_doc.name,
                    "item_name": existing_doc.item_name,
                    "item_group": existing_doc.item_group,
                },
            }

        # ── Resolve defaults ──────────────────────────────────────────────────
        resolved_name = item_name or item_code
        resolved_group = item_group or "All Item Groups"
        resolved_uom = stock_uom or "Nos"

        # ── Build doc ─────────────────────────────────────────────────────────
        doc_data = {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": resolved_name,
            "item_group": resolved_group,
            "stock_uom": resolved_uom,
            "is_stock_item": 1 if is_stock_item else 0,
        }

        if description:
            doc_data["description"] = description

        item_doc = frappe.get_doc(doc_data)

        # ── Item defaults (warehouse + valuation rate) ────────────────────────
        if default_warehouse or standard_rate is not None:
            company = self.company or frappe.defaults.get_defaults().get("company")
            item_default = {
                "company": company,
            }
            if default_warehouse:
                item_default["default_warehouse"] = default_warehouse
            if standard_rate is not None:
                item_default["buying_cost_center"] = None  # placeholder — rate set below
            item_doc.append("item_defaults", item_default)

        item_doc.insert(ignore_permissions=False)

        # ── Set standard rate via Item Price if provided ──────────────────────
        if standard_rate is not None:
            price_doc = frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": item_doc.name,
                    "price_list": "Standard Selling",
                    "selling": 1,
                    "price_list_rate": standard_rate,
                    "uom": resolved_uom,
                }
            )
            price_doc.insert(ignore_permissions=False)

        frappe.db.commit()

        result = {
            "created": True,
            "item_code": item_doc.name,
            "item_name": item_doc.item_name,
            "item_group": item_doc.item_group,
            "stock_uom": item_doc.stock_uom,
            "is_stock_item": bool(item_doc.is_stock_item),
        }

        if standard_rate is not None:
            result["standard_rate"] = standard_rate
            result["price_list"] = "Standard Selling"

        if default_warehouse:
            result["default_warehouse"] = default_warehouse

        return result
