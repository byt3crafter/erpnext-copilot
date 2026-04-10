import frappe
from frappe.utils import flt, today, add_to_date, getdate, formatdate
from erpnext_ai_bots.tools.base import BaseTool


class GetSalesDashboardTool(BaseTool):
    name = "sales.get_sales_dashboard"
    description = (
        "Quick daily sales snapshot. Shows today's sales vs same day last week, "
        "month-to-date sales vs last month same period, top selling items and "
        "top customers for the day. Use this when the user asks for a sales "
        "summary, daily performance, or 'how are we doing today'."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Company name. Defaults to the active company context.",
        },
        "date": {
            "type": "string",
            "description": "The date to report on in YYYY-MM-DD. Defaults to today.",
        },
        "territory": {
            "type": "string",
            "description": "Filter to a territory/branch (partial match).",
        },
    }
    required_params = []
    action_type = "Report"
    required_doctype = "Sales Invoice"
    required_ptype = "read"

    def execute(self, company=None, date=None, territory=None, **kwargs):
        frappe.has_permission("Sales Invoice", ptype="read", throw=True)

        company = company or self.company
        target_date = date or today()
        d = getdate(target_date)

        # Build optional territory filter
        territory_condition = ""
        params = {"company": company, "target_date": target_date}

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

        # 1. Today's sales
        today_sales = frappe.db.sql(f"""
            SELECT
                COUNT(*) AS invoice_count,
                IFNULL(SUM(si.grand_total), 0) AS total_sales,
                IFNULL(SUM(si.net_total), 0) AS net_sales
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date = %(target_date)s
              AND si.company = %(company)s
              {territory_condition}
        """, params, as_dict=True)[0]

        # 2. Same day last week
        last_week_date = str(add_to_date(d, days=-7))
        params["last_week_date"] = last_week_date
        last_week = frappe.db.sql(f"""
            SELECT
                COUNT(*) AS invoice_count,
                IFNULL(SUM(si.grand_total), 0) AS total_sales
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date = %(last_week_date)s
              AND si.company = %(company)s
              {territory_condition}
        """, params, as_dict=True)[0]

        # 3. Month-to-date
        mtd_start = d.replace(day=1).isoformat()
        params["mtd_start"] = mtd_start
        mtd = frappe.db.sql(f"""
            SELECT
                IFNULL(SUM(si.grand_total), 0) AS mtd_sales,
                COUNT(*) AS mtd_invoices
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date BETWEEN %(mtd_start)s AND %(target_date)s
              AND si.company = %(company)s
              {territory_condition}
        """, params, as_dict=True)[0]

        # 4. Last month same period
        last_month_date = add_to_date(d, months=-1)
        lm_start = getdate(last_month_date).replace(day=1).isoformat()
        lm_end = str(last_month_date)
        params["lm_start"] = lm_start
        params["lm_end"] = lm_end
        last_month = frappe.db.sql(f"""
            SELECT
                IFNULL(SUM(si.grand_total), 0) AS last_month_sales,
                COUNT(*) AS last_month_invoices
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date BETWEEN %(lm_start)s AND %(lm_end)s
              AND si.company = %(company)s
              {territory_condition}
        """, params, as_dict=True)[0]

        # 5. Top 5 items today
        top_items = frappe.db.sql(f"""
            SELECT
                sii.item_code,
                sii.item_name,
                SUM(sii.qty) AS qty_sold,
                SUM(sii.amount) AS revenue
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date = %(target_date)s
              AND si.company = %(company)s
              {territory_condition}
            GROUP BY sii.item_code, sii.item_name
            ORDER BY revenue DESC
            LIMIT 5
        """, params, as_dict=True)

        # 6. Top 5 customers today
        top_customers = frappe.db.sql(f"""
            SELECT
                si.customer,
                si.customer_name,
                SUM(si.grand_total) AS total
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date = %(target_date)s
              AND si.company = %(company)s
              {territory_condition}
            GROUP BY si.customer, si.customer_name
            ORDER BY total DESC
            LIMIT 5
        """, params, as_dict=True)

        # Compute deltas
        today_total = flt(today_sales.total_sales)
        lw_total = flt(last_week.total_sales)
        mtd_total = flt(mtd.mtd_sales)
        lm_total = flt(last_month.last_month_sales)

        wow_change = flt((today_total - lw_total) / lw_total * 100, 1) if lw_total else None
        mom_change = flt((mtd_total - lm_total) / lm_total * 100, 1) if lm_total else None

        return {
            "date": target_date,
            "company": company,
            "today": {
                "total_sales": flt(today_total, 2),
                "net_sales": flt(today_sales.net_sales, 2),
                "invoice_count": today_sales.invoice_count,
            },
            "vs_last_week": {
                "last_week_date": last_week_date,
                "last_week_sales": flt(lw_total, 2),
                "change_pct": wow_change,
            },
            "mtd": {
                "period": f"{mtd_start} to {target_date}",
                "mtd_sales": flt(mtd_total, 2),
                "mtd_invoices": mtd.mtd_invoices,
            },
            "vs_last_month": {
                "last_month_period": f"{lm_start} to {lm_end}",
                "last_month_sales": flt(lm_total, 2),
                "change_pct": mom_change,
            },
            "top_items": [
                {
                    "item_code": r.item_code,
                    "item_name": r.item_name,
                    "qty_sold": flt(r.qty_sold, 2),
                    "revenue": flt(r.revenue, 2),
                }
                for r in top_items
            ],
            "top_customers": [
                {
                    "customer": r.customer,
                    "customer_name": r.customer_name,
                    "total": flt(r.total, 2),
                }
                for r in top_customers
            ],
        }
