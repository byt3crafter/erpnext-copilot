import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetReorderLevelsTool(BaseTool):
    name = "stock.get_reorder_levels"
    description = (
        "Return items that have reorder levels configured, compared against their current stock "
        "from the Bin table. Each result includes the reorder level, reorder quantity, current "
        "stock on hand, and a shortage indicator for items that have fallen below their reorder "
        "level. Filter by item_code or warehouse, or omit both to check all items company-wide."
    )
    parameters = {
        "item_code": {
            "type": "string",
            "description": "Exact item code to check. Omit to check all items with reorder levels.",
        },
        "warehouse": {
            "type": "string",
            "description": "Warehouse to scope the check to. Omit to aggregate across all warehouses.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Item"
    required_ptype = "read"

    def execute(self, item_code=None, warehouse=None, **kwargs):
        frappe.has_permission("Item", ptype="read", throw=True)

        # Item Reorder is a child table on the Item doctype (doctype: "Item Reorder").
        reorder_filters = {}
        if item_code:
            reorder_filters["parent"] = item_code
        if warehouse:
            reorder_filters["warehouse"] = warehouse

        reorder_rows = frappe.get_all(
            "Item Reorder",
            filters=reorder_filters,
            fields=["parent as item_code", "warehouse", "warehouse_reorder_level", "warehouse_reorder_qty", "material_request_type"],
        )

        if not reorder_rows:
            return {
                "data": [],
                "total_items": 0,
                "items_below_reorder": 0,
                "message": "No reorder levels found for the given filters.",
            }

        # Build a set of (item_code, warehouse) pairs to query Bin efficiently.
        item_codes = list({r["item_code"] for r in reorder_rows})
        warehouses = list({r["warehouse"] for r in reorder_rows if r["warehouse"]})

        bin_filters = [["item_code", "in", item_codes]]
        if warehouses:
            bin_filters.append(["warehouse", "in", warehouses])

        bins = frappe.get_all(
            "Bin",
            filters=bin_filters,
            fields=["item_code", "warehouse", "actual_qty"],
        )

        # Build a lookup: (item_code, warehouse) -> actual_qty
        bin_lookup: dict = {}
        for b in bins:
            bin_lookup[(b["item_code"], b["warehouse"])] = b.get("actual_qty") or 0.0

        data = []
        items_below = 0

        for row in reorder_rows:
            current_qty = bin_lookup.get((row["item_code"], row["warehouse"]), 0.0)
            reorder_level = row.get("warehouse_reorder_level") or 0.0
            reorder_qty = row.get("warehouse_reorder_qty") or 0.0
            below_reorder = current_qty < reorder_level
            shortage = max(reorder_level - current_qty, 0.0)

            if below_reorder:
                items_below += 1

            data.append(
                {
                    "item_code": row["item_code"],
                    "warehouse": row["warehouse"],
                    "reorder_level": reorder_level,
                    "reorder_qty": reorder_qty,
                    "material_request_type": row.get("material_request_type"),
                    "current_qty": current_qty,
                    "below_reorder": below_reorder,
                    "shortage": shortage,
                }
            )

        # Sort: items below reorder level first, then by shortage descending.
        data.sort(key=lambda r: (not r["below_reorder"], -r["shortage"]))

        return {
            "data": data,
            "total_items": len(data),
            "items_below_reorder": items_below,
        }
