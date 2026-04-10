import frappe
from erpnext_ai_bots.tools.base import BaseTool


_ITEM_FIELDS = [
    "item_code",
    "item_name",
    "item_group",
    "stock_uom",
    "is_stock_item",
    "valuation_rate",
    "description",
    "disabled",
    "has_variants",
    "variant_of",
]


class GetItemInfoTool(BaseTool):
    name = "stock.get_item_info"
    description = (
        "Retrieve item master information from ERPNext. "
        "Provide item_code for an exact lookup, or use item_name and/or item_group for a search. "
        "Returns up to 20 results when searching, or a single record for an exact item_code lookup."
    )
    parameters = {
        "item_code": {
            "type": "string",
            "description": "Exact item code for a direct lookup. When supplied, item_name and item_group are ignored.",
        },
        "item_name": {
            "type": "string",
            "description": "Partial or full item name to search for. Case-insensitive substring match.",
        },
        "item_group": {
            "type": "string",
            "description": "Exact item group name to filter the search results.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Item"
    required_ptype = "read"

    def execute(self, item_code=None, item_name=None, item_group=None, **kwargs):
        frappe.has_permission("Item", ptype="read", throw=True)

        if item_code:
            doc = frappe.get_doc("Item", item_code)
            return {
                "data": [
                    {
                        "item_code": doc.item_code,
                        "item_name": doc.item_name,
                        "item_group": doc.item_group,
                        "stock_uom": doc.stock_uom,
                        "is_stock_item": doc.is_stock_item,
                        "valuation_rate": doc.valuation_rate,
                        "description": doc.description,
                        "disabled": doc.disabled,
                        "has_variants": doc.has_variants,
                        "variant_of": doc.variant_of,
                    }
                ],
                "total_rows": 1,
                "showing": 1,
            }

        filters = {}
        if item_group:
            filters["item_group"] = item_group

        or_filters = {}
        if item_name:
            or_filters["item_name"] = ["like", f"%{item_name}%"]
            or_filters["item_code"] = ["like", f"%{item_name}%"]

        # frappe.get_all does not support or_filters as a dict when filters is
        # also present, so we build a single filter list when both are needed.
        if filters and or_filters:
            # Combine: item_group AND (item_name LIKE ... OR item_code LIKE ...)
            filter_list = [["Item", "item_group", "=", item_group]]
            name_conditions = [
                ["Item", "item_name", "like", f"%{item_name}%"],
            ]
            items = frappe.get_all(
                "Item",
                filters=filter_list,
                or_filters=name_conditions,
                fields=_ITEM_FIELDS,
                limit=20,
            )
        elif or_filters:
            items = frappe.get_all(
                "Item",
                or_filters=[
                    ["Item", "item_name", "like", f"%{item_name}%"],
                    ["Item", "item_code", "like", f"%{item_name}%"],
                ],
                fields=_ITEM_FIELDS,
                limit=20,
            )
        else:
            items = frappe.get_all(
                "Item",
                filters=filters,
                fields=_ITEM_FIELDS,
                limit=20,
            )

        return {
            "data": items,
            "total_rows": len(items),
            "showing": len(items),
        }
