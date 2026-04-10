import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetAccountBalanceTool(BaseTool):
    name = "accounting.get_account_balance"
    description = (
        "Return the running balance of a specific GL Account as of a given date. "
        "Uses ERPNext's native get_balance_on utility so period-closing entries are respected."
    )
    parameters = {
        "account": {
            "type": "string",
            "description": "Full GL Account name as stored in ERPNext, e.g. 'Cash - ACME'.",
        },
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext.",
        },
        "as_of": {
            "type": "string",
            "description": "Date up to which the balance is calculated, in YYYY-MM-DD format.",
        },
    }
    required_params = ["account", "company", "as_of"]
    action_type = "Read"
    required_doctype = "Account"
    required_ptype = "read"

    def execute(self, account, company, as_of, **kwargs):
        frappe.has_permission("Account", ptype="read", throw=True)

        from erpnext.accounts.utils import get_balance_on

        balance = get_balance_on(account=account, date=as_of, company=company)

        return {
            "account": account,
            "company": company,
            "as_of": as_of,
            "balance": balance,
        }
