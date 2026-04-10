import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetTrialBalanceTool(BaseTool):
    name = "accounting.get_trial_balance"
    description = (
        "Fetch the Trial Balance report for a company over a date range. "
        "Returns up to 100 account rows with their opening, debit, credit, and closing balances, "
        "plus aggregate totals for the period."
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

        result = frappe.call(
            "frappe.desk.query_report.run",
            report_name="Trial Balance",
            filters={
                "company": company,
                "from_date": from_date,
                "to_date": to_date,
                "with_period_closing_entry": 0,
            },
        )

        rows = result.get("result", [])
        data = rows[:100]

        total_debit = 0.0
        total_credit = 0.0
        for row in rows:
            if isinstance(row, dict):
                total_debit += row.get("debit", 0) or 0
                total_credit += row.get("credit", 0) or 0

        return {
            "data": data,
            "total_rows": len(rows),
            "showing": len(data),
            "total_debit": total_debit,
            "total_credit": total_credit,
        }
