import frappe
from frappe.utils import flt, today, add_to_date
from erpnext_ai_bots.tools.base import BaseTool


class GetInventoryDaysTool(BaseTool):
    name = "stock.get_inventory_days"
    description = (
        "Calculate days of stock cover (inventory days) based on current stock "
        "and recent sales velocity. Classifies items as fast, medium, or slow movers. "
        "Days of stock = Current Stock Qty / Average Daily Sales Qty. "
        "Use this when the user asks about stock cover, how long stock will last, "
        "dead stock, slow movers, or inventory health."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Company name. Defaults to the active company context.",
        },
        "warehouse": {
            "type": "string",
            "description": "Filter by warehouse (partial match).",
        },
        "item_group": {
            "type": "string",
            "description": "Filter by item group.",
        },
        "item_code": {
            "type": "string",
            "description": "Filter to a specific item.",
        },
        "velocity_days": {
            "type": "integer",
            "description": "Number of past days to compute sales velocity. Default 30.",
        },
        "limit": {
            "type": "integer",
            "description": "Max items to return. Default 50.",
        },
    }
    required_params = []
    action_type = "Report"
    required_doctype = "Stock Ledger Entry"
    required_ptype = "read"

    def execute(self, company=None, warehouse=None, item_group=None,
                item_code=None, velocity_days=None, limit=None, **kwargs):
        frappe.has_permission("Stock Ledger Entry", ptype="read", throw=True)

        company = company or self.company
        velocity_days = int(velocity_days or 30)
        limit = min(int(limit or 50), 100)

        params = {"company": company}
        stock_conditions = []
        sales_conditions = []

        if warehouse:
            params["warehouse"] = f"%{warehouse}%"
            stock_conditions.append("AND w.name LIKE %(warehouse)s")

        if item_group:
            params["item_group"] = item_group
            stock_conditions.append("AND i.item_group = %(item_group)s")
            sales_conditions.append("AND i.item_group = %(item_group)s")

        if item_code:
            params["item_code"] = item_code
            stock_conditions.append("AND b.item_code = %(item_code)s")
            sales_conditions.append("AND sii.item_code = %(item_code)s")

        stock_where = " ".join(stock_conditions)
        sales_where = " ".join(sales_conditions)

        # 1. Current stock from tabBin
        stock_data = frappe.db.sql(f"""
            SELECT
                b.item_code,
                i.item_name,
                i.item_group,
                SUM(b.actual_qty) AS total_qty,
                SUM(b.stock_value) AS stock_value,
                AVG(b.valuation_rate) AS avg_valuation_rate
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            JOIN `tabWarehouse` w ON w.name = b.warehouse
            WHERE b.actual_qty > 0
              AND w.company = %(company)s
              {stock_where}
            GROUP BY b.item_code, i.item_name, i.item_group
        """, params, as_dict=True)

        if not stock_data:
            return {
                "company": company,
                "total_items": 0,
                "total_stock_value": 0,
                "items": [],
                "note": "No stock found for the given filters.",
            }

        # 2. Sales velocity from recent invoices
        velocity_start = str(add_to_date(today(), days=-velocity_days))
        params["velocity_start"] = velocity_start

        sales_data = frappe.db.sql(f"""
            SELECT
                sii.item_code,
                SUM(sii.qty) AS total_sold
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            JOIN `tabItem` i ON i.name = sii.item_code
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date >= %(velocity_start)s
              AND si.company = %(company)s
              {sales_where}
            GROUP BY sii.item_code
        """, params, as_dict=True)

        sales_map = {r.item_code: flt(r.total_sold) for r in sales_data}

        # 3. Calculate inventory days and classify
        items = []
        total_stock_value = 0

        for row in stock_data:
            qty = flt(row.total_qty)
            value = flt(row.stock_value)
            total_stock_value += value

            total_sold = sales_map.get(row.item_code, 0)
            avg_daily_sales = total_sold / velocity_days if velocity_days else 0

            if avg_daily_sales > 0:
                days_of_stock = flt(qty / avg_daily_sales, 1)
            else:
                days_of_stock = 9999  # No sales = effectively infinite

            # Classify
            if avg_daily_sales == 0:
                classification = "no_sales"
            elif days_of_stock < 30:
                classification = "fast_mover"
            elif days_of_stock < 90:
                classification = "medium_mover"
            else:
                classification = "slow_mover"

            items.append({
                "item_code": row.item_code,
                "item_name": row.item_name,
                "item_group": row.item_group,
                "current_qty": flt(qty, 2),
                "stock_value": flt(value, 2),
                "total_sold_last_n_days": flt(total_sold, 2),
                "avg_daily_sales": flt(avg_daily_sales, 2),
                "days_of_stock": days_of_stock if days_of_stock < 9999 else None,
                "classification": classification,
            })

        # Sort: fast movers first (low days), then medium, then slow, then no_sales
        class_order = {"fast_mover": 0, "medium_mover": 1, "slow_mover": 2, "no_sales": 3}
        items.sort(key=lambda x: (class_order.get(x["classification"], 4),
                                   x.get("days_of_stock") or 9999))

        # Summary counts
        fast = sum(1 for x in items if x["classification"] == "fast_mover")
        medium = sum(1 for x in items if x["classification"] == "medium_mover")
        slow = sum(1 for x in items if x["classification"] == "slow_mover")
        no_sales = sum(1 for x in items if x["classification"] == "no_sales")

        return {
            "company": company,
            "velocity_period_days": velocity_days,
            "total_items": len(items),
            "total_stock_value": flt(total_stock_value, 2),
            "classification_summary": {
                "fast_movers": fast,
                "medium_movers": medium,
                "slow_movers": slow,
                "no_sales": no_sales,
            },
            "items": items[:limit],
        }
