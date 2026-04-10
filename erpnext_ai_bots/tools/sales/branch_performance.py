import frappe
from frappe.utils import flt, today, getdate
from erpnext_ai_bots.tools.base import BaseTool


class GetBranchPerformanceTool(BaseTool):
    name = "sales.get_branch_performance"
    description = (
        "Compare sales performance across branches (territories or cost centers). "
        "Returns daily and period sales per branch ranked best to worst, with "
        "gross profit per branch. Use this when the user asks about branch "
        "performance, branch ranking, which branch is doing best/worst, or "
        "territory-level comparison."
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
        "branch_field": {
            "type": "string",
            "description": "Field to group by: 'territory' (default) or 'cost_center'.",
            "enum": ["territory", "cost_center"],
        },
        "include_profit": {
            "type": "boolean",
            "description": "Include gross profit per branch. Default true.",
        },
        "territory": {
            "type": "string",
            "description": "Filter to specific territory/branch (partial match).",
        },
    }
    required_params = ["from_date", "to_date"]
    action_type = "Report"
    required_doctype = "Sales Invoice"
    required_ptype = "read"

    def execute(self, from_date, to_date, company=None, branch_field=None,
                include_profit=True, territory=None, **kwargs):
        frappe.has_permission("Sales Invoice", ptype="read", throw=True)

        company = company or self.company
        branch_col = branch_field or "territory"
        if branch_col not in ("territory", "cost_center"):
            branch_col = "territory"

        params = {"company": company, "from_date": from_date, "to_date": to_date}
        territory_condition = ""

        if territory:
            territories = frappe.get_all(
                "Territory",
                filters={"name": ["like", f"%{territory}%"]},
                pluck="name",
            )
            if not territories:
                return {"error": f"No territory found matching '{territory}'."}
            params["territories"] = territories
            territory_condition = "AND si.territory IN %(territories)s"

        # Period sales + profit by branch
        profit_cols = ""
        profit_join = ""
        if include_profit:
            profit_cols = (
                ", SUM(sii.amount) AS item_revenue"
                ", SUM(sii.qty * IFNULL(sii.incoming_rate, 0)) AS total_cogs"
            )
            profit_join = "JOIN `tabSales Invoice Item` sii ON sii.parent = si.name"

        period_data = frappe.db.sql(f"""
            SELECT
                si.{branch_col} AS branch,
                COUNT(DISTINCT si.name) AS invoice_count,
                SUM(si.grand_total) AS total_sales
                {profit_cols}
            FROM `tabSales Invoice` si
            {profit_join}
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.company = %(company)s
              {territory_condition}
            GROUP BY si.{branch_col}
            ORDER BY total_sales DESC
        """, params, as_dict=True)

        # Today's sales by branch
        params["today"] = today()
        today_data = frappe.db.sql(f"""
            SELECT
                si.{branch_col} AS branch,
                SUM(si.grand_total) AS daily_sales,
                COUNT(*) AS invoice_count
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date = %(today)s
              AND si.company = %(company)s
              {territory_condition}
            GROUP BY si.{branch_col}
            ORDER BY daily_sales DESC
        """, params, as_dict=True)

        today_map = {r.branch: r for r in today_data}

        # Build ranked results
        ranking = []
        for rank, row in enumerate(period_data, 1):
            branch = row.branch or "Unknown"
            total_sales = flt(row.total_sales, 2)
            entry = {
                "rank": rank,
                "branch": branch,
                "period_sales": total_sales,
                "period_invoices": row.invoice_count,
                "today_sales": flt(today_map.get(branch, {}).get("daily_sales"), 2),
            }
            if include_profit and row.get("item_revenue"):
                revenue = flt(row.item_revenue)
                cogs = flt(row.total_cogs)
                gross_profit = revenue - cogs
                margin_pct = flt(gross_profit / revenue * 100, 1) if revenue else 0
                entry["gross_profit"] = flt(gross_profit, 2)
                entry["margin_pct"] = margin_pct
            ranking.append(entry)

        grand_total = sum(r["period_sales"] for r in ranking)

        return {
            "company": company,
            "period": f"{from_date} to {to_date}",
            "branch_field": branch_col,
            "grand_total_sales": flt(grand_total, 2),
            "branch_count": len(ranking),
            "ranking": ranking,
        }
