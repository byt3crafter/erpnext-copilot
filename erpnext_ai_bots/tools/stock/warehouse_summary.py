import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetWarehouseSummaryTool(BaseTool):
    name = "stock.get_warehouse_summary"
    description = (
        "Return a summary of warehouses for a company, including their hierarchical position "
        "and current stock levels aggregated from the Bin table. "
        "Filter by a specific warehouse name, or omit to retrieve all warehouses for the company."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext. Defaults to the bot's active company.",
        },
        "warehouse": {
            "type": "string",
            "description": "Exact warehouse name to filter on. Omit to return all warehouses.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Warehouse"
    required_ptype = "read"

    def execute(self, company=None, warehouse=None, **kwargs):
        frappe.has_permission("Warehouse", ptype="read", throw=True)

        wh_filters = {"company": company or self.company, "is_group": 0}
        if warehouse:
            wh_filters["name"] = warehouse

        warehouses = frappe.get_all(
            "Warehouse",
            filters=wh_filters,
            fields=["name", "warehouse_name", "parent_warehouse", "lft", "rgt", "disabled"],
            order_by="lft asc",
        )

        if not warehouses:
            return {"data": [], "total_warehouses": 0}

        warehouse_names = [w["name"] for w in warehouses]

        # Aggregate Bin data: total actual_qty and total_value per warehouse.
        bins = frappe.get_all(
            "Bin",
            filters=[["warehouse", "in", warehouse_names]],
            fields=["warehouse", "actual_qty", "stock_value"],
        )

        # Roll up bin totals into a lookup keyed by warehouse name.
        stock_by_warehouse: dict = {}
        for b in bins:
            wh = b["warehouse"]
            if wh not in stock_by_warehouse:
                stock_by_warehouse[wh] = {"total_actual_qty": 0.0, "total_stock_value": 0.0, "distinct_items": 0}
            stock_by_warehouse[wh]["total_actual_qty"] += b.get("actual_qty") or 0
            stock_by_warehouse[wh]["total_stock_value"] += b.get("stock_value") or 0
            stock_by_warehouse[wh]["distinct_items"] += 1

        data = []
        for w in warehouses:
            wh_name = w["name"]
            stock = stock_by_warehouse.get(wh_name, {})
            data.append(
                {
                    "name": wh_name,
                    "warehouse_name": w["warehouse_name"],
                    "parent_warehouse": w["parent_warehouse"],
                    "lft": w["lft"],
                    "rgt": w["rgt"],
                    "disabled": w["disabled"],
                    "total_actual_qty": stock.get("total_actual_qty", 0.0),
                    "total_stock_value": stock.get("total_stock_value", 0.0),
                    "distinct_items": stock.get("distinct_items", 0),
                }
            )

        return {
            "data": data,
            "total_warehouses": len(data),
            "company": company or self.company,
        }
