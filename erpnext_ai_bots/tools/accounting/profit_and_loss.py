import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetProfitAndLossTool(BaseTool):
    name = "accounting.get_profit_and_loss"
    description = (
        "Fetch the Profit and Loss Statement for a company over a given date range. "
        "Returns income, expense, and net profit/loss rows (up to 100 rows shown). "
        "The fiscal year is resolved automatically from the supplied dates."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext.",
        },
        "from_date": {
            "type": "string",
            "description": "Start date of the reporting period in YYYY-MM-DD format.",
        },
        "to_date": {
            "type": "string",
            "description": "End date of the reporting period in YYYY-MM-DD format.",
        },
    }
    required_params = ["company", "from_date", "to_date"]
    action_type = "Report"
    required_doctype = "Account"
    required_ptype = "read"

    def execute(self, company, from_date, to_date, **kwargs):
        frappe.has_permission("Account", ptype="read", throw=True)

        # Resolve the fiscal year that contains to_date so the report engine
        # does not reject the request with a missing fiscal year error.
        fiscal_year = frappe.db.get_value(
            "Fiscal Year",
            {
                "year_start_date": ["<=", to_date],
                "year_end_date": [">=", to_date],
                "disabled": 0,
            },
            "name",
        )
        if not fiscal_year:
            frappe.throw(
                f"No active Fiscal Year found that contains the date {to_date}. "
                "Please configure a Fiscal Year in ERPNext before running this report."
            )

        result = frappe.call(
            "frappe.desk.query_report.run",
            report_name="Profit and Loss Statement",
            filters={
                "company": company,
                "from_date": from_date,
                "to_date": to_date,
                "fiscal_year": fiscal_year,
                "period_start_date": from_date,
                "period_end_date": to_date,
            },
        )

        rows = result.get("result", [])
        data = rows[:100]

        return {
            "fiscal_year": fiscal_year,
            "data": data,
            "total_rows": len(rows),
            "showing": len(data),
            "columns": [
                c.get("label", c.get("fieldname", "")) if isinstance(c, dict) else str(c)
                for c in result.get("columns", [])
            ],
        }
