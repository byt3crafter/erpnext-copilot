import frappe
from frappe.utils import flt
from erpnext_ai_bots.tools.base import BaseTool


class GetGrossMarginTool(BaseTool):
    name = "accounting.get_gross_margin"
    description = (
        "Calculate gross profit margin from submitted Sales Invoices. "
        "Returns overall gross profit percentage, and optionally breaks "
        "down margin by territory (branch), item group, or daily. "
        "Gross Margin = (Revenue - Cost of Goods) / Revenue * 100. "
        "Use this when the user asks about profit margin, gross profit, "
        "or margin analysis."
    )
    parameters = {
        "from_date": {
            "type": "string",
            "description": "Start date YYYY-MM-DD.",
        },
        "to_date": {
            "type": "string",
            "description": "End date YYYY-MM-DD.",
        },
        "company": {
            "type": "string",
            "description": "Company name. Defaults to the active company context.",
        },
        "territory": {
            "type": "string",
            "description": "Filter by territory/branch (partial match).",
        },
        "item_group": {
            "type": "string",
            "description": "Filter by item group (partial match).",
        },
        "group_by": {
            "type": "string",
            "description": (
                "Group results by: 'territory', 'item_group', 'daily', "
                "or omit for overall summary."
            ),
            "enum": ["territory", "item_group", "daily"],
        },
    }
    required_params = ["from_date", "to_date"]
    action_type = "Report"
    required_doctype = "Sales Invoice"
    required_ptype = "read"

    def execute(self, from_date, to_date, company=None, territory=None,
                item_group=None, group_by=None, **kwargs):
        frappe.has_permission("Sales Invoice", ptype="read", throw=True)

        company = company or self.company
        params = {"company": company, "from_date": from_date, "to_date": to_date}
        conditions = []

        if territory:
            territories = frappe.get_all(
                "Territory",
                filters={"name": ["like", f"%{territory}%"]},
                pluck="name",
            )
            if not territories:
                return {"error": f"No territory found matching '{territory}'."}
            params["territories"] = territories
            conditions.append("AND si.territory IN %(territories)s")

        if item_group:
            params["item_group"] = f"%{item_group}%"
            conditions.append("AND sii.item_group LIKE %(item_group)s")

        extra_where = " ".join(conditions)

        # Determine GROUP BY / SELECT
        if group_by == "territory":
            select_col = "si.territory AS group_label,"
            group_clause = "GROUP BY si.territory"
            order_clause = "ORDER BY revenue DESC"
        elif group_by == "item_group":
            select_col = "sii.item_group AS group_label,"
            group_clause = "GROUP BY sii.item_group"
            order_clause = "ORDER BY revenue DESC"
        elif group_by == "daily":
            select_col = "si.posting_date AS group_label,"
            group_clause = "GROUP BY si.posting_date"
            order_clause = "ORDER BY si.posting_date"
        else:
            select_col = ""
            group_clause = ""
            order_clause = ""

        rows = frappe.db.sql(f"""
            SELECT
                {select_col}
                SUM(sii.amount) AS revenue,
                SUM(sii.qty * IFNULL(sii.incoming_rate, 0)) AS cogs
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.company = %(company)s
              {extra_where}
            {group_clause}
            {order_clause}
            LIMIT 100
        """, params, as_dict=True)

        # Calculate margins
        breakdown = []
        total_revenue = 0
        total_cogs = 0

        for row in rows:
            revenue = flt(row.revenue)
            cogs = flt(row.cogs)
            gross_profit = revenue - cogs
            margin_pct = flt(gross_profit / revenue * 100, 2) if revenue else 0

            total_revenue += revenue
            total_cogs += cogs

            entry = {
                "revenue": flt(revenue, 2),
                "cogs": flt(cogs, 2),
                "gross_profit": flt(gross_profit, 2),
                "margin_pct": margin_pct,
            }
            if group_by:
                entry["label"] = str(row.group_label) if row.group_label else "Unknown"
            breakdown.append(entry)

        overall_profit = total_revenue - total_cogs
        overall_margin = flt(overall_profit / total_revenue * 100, 2) if total_revenue else 0

        result = {
            "company": company,
            "period": f"{from_date} to {to_date}",
            "summary": {
                "total_revenue": flt(total_revenue, 2),
                "total_cogs": flt(total_cogs, 2),
                "gross_profit": flt(overall_profit, 2),
                "margin_pct": overall_margin,
            },
        }

        if group_by:
            result["group_by"] = group_by
            result["breakdown"] = breakdown

        if territory:
            result["territory_filter"] = territory
        if item_group:
            result["item_group_filter"] = item_group

        return result
