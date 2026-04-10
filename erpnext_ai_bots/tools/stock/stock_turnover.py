import frappe
from frappe.utils import flt, date_diff
from erpnext_ai_bots.tools.base import BaseTool


class GetStockTurnoverTool(BaseTool):
    name = "stock.get_stock_turnover"
    description = (
        "Calculate stock turnover rate: COGS / Average Inventory Value. "
        "Higher turnover means inventory sells and is replaced faster. "
        "Can group by item group or warehouse, and optionally compare two periods. "
        "Use this when the user asks about inventory efficiency, stock turnover, "
        "or how fast stock is moving."
    )
    parameters = {
        "from_date": {
            "type": "string",
            "description": "Start date YYYY-MM-DD for the period.",
        },
        "to_date": {
            "type": "string",
            "description": "End date YYYY-MM-DD for the period.",
        },
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
        "group_by": {
            "type": "string",
            "description": "Group by 'item_group' or 'warehouse'. Omit for overall turnover.",
            "enum": ["item_group", "warehouse"],
        },
        "compare_from_date": {
            "type": "string",
            "description": "Start of comparison period YYYY-MM-DD.",
        },
        "compare_to_date": {
            "type": "string",
            "description": "End of comparison period YYYY-MM-DD.",
        },
    }
    required_params = ["from_date", "to_date"]
    action_type = "Report"
    required_doctype = "Stock Ledger Entry"
    required_ptype = "read"

    def execute(self, from_date, to_date, company=None, warehouse=None,
                item_group=None, group_by=None, compare_from_date=None,
                compare_to_date=None, **kwargs):
        frappe.has_permission("Stock Ledger Entry", ptype="read", throw=True)

        company = company or self.company

        current = self._compute_turnover(
            from_date, to_date, company, warehouse, item_group, group_by
        )

        result = {
            "company": company,
            "period": f"{from_date} to {to_date}",
            "period_days": date_diff(to_date, from_date) + 1,
            **current,
        }

        if compare_from_date and compare_to_date:
            comparison = self._compute_turnover(
                compare_from_date, compare_to_date, company,
                warehouse, item_group, group_by
            )
            result["comparison"] = {
                "period": f"{compare_from_date} to {compare_to_date}",
                "period_days": date_diff(compare_to_date, compare_from_date) + 1,
                **comparison,
            }

        return result

    def _compute_turnover(self, from_date, to_date, company, warehouse,
                          item_group, group_by):
        params = {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        }
        conditions = []

        if warehouse:
            params["warehouse"] = f"%{warehouse}%"
            conditions.append("AND sle.warehouse LIKE %(warehouse)s")

        if item_group:
            params["item_group"] = item_group
            conditions.append("AND i.item_group = %(item_group)s")

        extra_where = " ".join(conditions)
        period_days = date_diff(to_date, from_date) + 1

        # Determine grouping
        if group_by == "item_group":
            select_col = "i.item_group AS group_label,"
            group_clause = "GROUP BY i.item_group"
        elif group_by == "warehouse":
            select_col = "sle.warehouse AS group_label,"
            group_clause = "GROUP BY sle.warehouse"
        else:
            select_col = ""
            group_clause = ""

        # COGS: outgoing stock value from Sales Invoice entries
        cogs_data = frappe.db.sql(f"""
            SELECT
                {select_col}
                SUM(ABS(sle.stock_value_difference)) AS cogs
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND sle.voucher_type = 'Sales Invoice'
              AND sle.actual_qty < 0
              AND sle.company = %(company)s
              {extra_where}
            {group_clause}
        """, params, as_dict=True)

        # Opening inventory value (sum of all SLE up to from_date)
        opening_data = frappe.db.sql(f"""
            SELECT
                {select_col}
                SUM(sle.stock_value_difference) AS inventory_value
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.posting_date < %(from_date)s
              AND sle.company = %(company)s
              {extra_where}
            {group_clause}
        """, params, as_dict=True)

        # Closing inventory value (sum of all SLE up to to_date)
        closing_data = frappe.db.sql(f"""
            SELECT
                {select_col}
                SUM(sle.stock_value_difference) AS inventory_value
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.posting_date <= %(to_date)s
              AND sle.company = %(company)s
              {extra_where}
            {group_clause}
        """, params, as_dict=True)

        if not group_by:
            # Single row results
            cogs = flt(cogs_data[0].cogs) if cogs_data else 0
            opening = flt(opening_data[0].inventory_value) if opening_data else 0
            closing = flt(closing_data[0].inventory_value) if closing_data else 0
            avg_inventory = (opening + closing) / 2 if (opening + closing) else 0

            turnover_rate = flt(cogs / avg_inventory, 2) if avg_inventory else 0
            days_to_sell = flt(period_days / turnover_rate, 1) if turnover_rate else None

            return {
                "summary": {
                    "cogs": flt(cogs, 2),
                    "opening_inventory": flt(opening, 2),
                    "closing_inventory": flt(closing, 2),
                    "avg_inventory": flt(avg_inventory, 2),
                    "turnover_rate": turnover_rate,
                    "days_to_sell_inventory": days_to_sell,
                },
            }
        else:
            # Group results — merge by group_label
            cogs_map = {r.group_label: flt(r.cogs) for r in cogs_data if r.group_label}
            opening_map = {r.group_label: flt(r.inventory_value) for r in opening_data if r.group_label}
            closing_map = {r.group_label: flt(r.inventory_value) for r in closing_data if r.group_label}

            all_labels = set(cogs_map) | set(opening_map) | set(closing_map)

            breakdown = []
            total_cogs = 0
            total_avg_inv = 0

            for label in sorted(all_labels):
                cogs = cogs_map.get(label, 0)
                opening = opening_map.get(label, 0)
                closing = closing_map.get(label, 0)
                avg_inv = (opening + closing) / 2 if (opening + closing) else 0

                total_cogs += cogs
                total_avg_inv += avg_inv

                turnover = flt(cogs / avg_inv, 2) if avg_inv else 0
                days = flt(period_days / turnover, 1) if turnover else None

                breakdown.append({
                    "label": label,
                    "cogs": flt(cogs, 2),
                    "avg_inventory": flt(avg_inv, 2),
                    "turnover_rate": turnover,
                    "days_to_sell_inventory": days,
                })

            # Sort by turnover rate descending (best first)
            breakdown.sort(key=lambda x: x["turnover_rate"], reverse=True)

            overall_turnover = flt(total_cogs / total_avg_inv, 2) if total_avg_inv else 0
            overall_days = flt(period_days / overall_turnover, 1) if overall_turnover else None

            return {
                "summary": {
                    "total_cogs": flt(total_cogs, 2),
                    "total_avg_inventory": flt(total_avg_inv, 2),
                    "overall_turnover_rate": overall_turnover,
                    "overall_days_to_sell": overall_days,
                },
                "group_by": group_by,
                "breakdown": breakdown[:50],
            }
