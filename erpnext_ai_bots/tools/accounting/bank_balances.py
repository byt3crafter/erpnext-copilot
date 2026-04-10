import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetBankBalancesTool(BaseTool):
    name = "accounting.get_bank_balances"
    description = (
        "Retrieve bank account balances for a company. "
        "Fetches all company-owned bank accounts and their current book balances. "
        "Optionally filter to a single bank account by name."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext.",
        },
        "bank_account": {
            "type": "string",
            "description": "Specific Bank Account document name to filter to. Omit to fetch all.",
        },
    }
    required_params = ["company"]
    action_type = "Read"
    required_doctype = "Bank Account"
    required_ptype = "read"

    def execute(self, company, bank_account=None, **kwargs):
        frappe.has_permission("Bank Account", ptype="read", throw=True)

        filters = {
            "company": company,
            "is_company_account": 1,
        }
        if bank_account:
            filters["name"] = bank_account

        accounts = frappe.get_all(
            "Bank Account",
            filters=filters,
            fields=[
                "name",
                "account_name",
                "bank",
                "account",
                "account_currency",
                "balance",
                "is_default",
            ],
            order_by="is_default desc, account_name asc",
        )

        # Fetch the GL balance for each linked ledger account when available
        for acc in accounts:
            ledger = acc.get("account")
            if ledger:
                acc["gl_balance"] = frappe.db.get_value(
                    "GL Entry",
                    {"account": ledger, "is_cancelled": 0},
                    "sum(debit) - sum(credit)",
                )

        total_balance = sum(
            (acc.get("gl_balance") or acc.get("balance") or 0) for acc in accounts
        )

        return {
            "company": company,
            "accounts": accounts,
            "count": len(accounts),
            "total_balance": total_balance,
        }
