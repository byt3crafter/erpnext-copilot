import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateJournalEntryTool(BaseTool):
    name = "accounting.create_journal_entry"
    description = (
        "Create a draft Journal Entry in ERPNext. "
        "Total debits must equal total credits (within a 0.01 tolerance). "
        "The entry is saved as a draft and must be submitted separately by the user."
    )
    parameters = {
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext.",
        },
        "posting_date": {
            "type": "string",
            "description": "Posting date for the Journal Entry in YYYY-MM-DD format.",
        },
        "entries": {
            "type": "array",
            "description": (
                "List of accounting line items. Each item must include 'account' and at least one of "
                "'debit_in_account_currency' or 'credit_in_account_currency'."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "account": {
                        "type": "string",
                        "description": "GL Account name.",
                    },
                    "debit_in_account_currency": {
                        "type": "number",
                        "description": "Debit amount in the account's currency.",
                    },
                    "credit_in_account_currency": {
                        "type": "number",
                        "description": "Credit amount in the account's currency.",
                    },
                    "party_type": {
                        "type": "string",
                        "description": "Party type, e.g. 'Customer', 'Supplier', 'Employee'.",
                    },
                    "party": {
                        "type": "string",
                        "description": "Party name matching the party_type.",
                    },
                },
                "required": ["account"],
            },
        },
        "user_remark": {
            "type": "string",
            "description": "Optional free-text remark to attach to the Journal Entry.",
        },
    }
    required_params = ["company", "posting_date", "entries"]
    action_type = "Create"
    required_doctype = "Journal Entry"
    required_ptype = "create"

    def execute(self, company, posting_date, entries, user_remark=None, **kwargs):
        frappe.has_permission("Journal Entry", ptype="create", throw=True)

        if not entries:
            frappe.throw("At least two accounting entries are required to create a Journal Entry.")

        total_debit = sum(e.get("debit_in_account_currency", 0) or 0 for e in entries)
        total_credit = sum(e.get("credit_in_account_currency", 0) or 0 for e in entries)

        if abs(total_debit - total_credit) > 0.01:
            frappe.throw(
                f"Journal Entry is unbalanced: total debit {total_debit:.2f} "
                f"does not equal total credit {total_credit:.2f}. "
                f"Difference: {abs(total_debit - total_credit):.4f}."
            )

        accounts = []
        for line in entries:
            row = {
                "account": line.get("account"),
                "debit_in_account_currency": line.get("debit_in_account_currency", 0) or 0,
                "credit_in_account_currency": line.get("credit_in_account_currency", 0) or 0,
            }
            if line.get("party_type"):
                row["party_type"] = line["party_type"]
            if line.get("party"):
                row["party"] = line["party"]
            accounts.append(row)

        doc_values = {
            "doctype": "Journal Entry",
            "company": company,
            "posting_date": posting_date,
            "accounts": accounts,
        }
        if user_remark:
            doc_values["user_remark"] = user_remark

        doc = frappe.get_doc(doc_values)
        doc.insert()

        return {
            "status": "created",
            "name": doc.name,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "message": (
                f"Draft Journal Entry '{doc.name}' created successfully. "
                "Please review and submit it from the ERPNext desk."
            ),
        }
