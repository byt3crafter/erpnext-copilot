import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetGeneralLedgerTool(BaseTool):
    name = "accounting.get_general_ledger"
    description = (
        "Get General Ledger entries for an account, party, or voucher. "
        "Useful to audit transactions, trace postings, or investigate account movements."
    )
    parameters = {
        "account": {
            "type": "string",
            "description": "GL Account name to filter by (optional)",
        },
        "party_type": {
            "type": "string",
            "description": "Party type: Customer, Supplier, Employee (optional)",
        },
        "party": {
            "type": "string",
            "description": "Party name to filter by (optional)",
        },
        "voucher_type": {
            "type": "string",
            "description": "e.g. Sales Invoice, Payment Entry, Journal Entry (optional)",
        },
        "voucher_no": {
            "type": "string",
            "description": "Specific voucher/document name to look up (optional)",
        },
        "from_date": {
            "type": "string",
            "description": "Start date in YYYY-MM-DD format (optional)",
        },
        "to_date": {
            "type": "string",
            "description": "End date in YYYY-MM-DD format (optional)",
        },
        "company": {
            "type": "string",
            "description": "Company name (optional, defaults to session company)",
        },
        "limit": {
            "type": "integer",
            "description": "Max entries to return (default 50, max 200)",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "GL Entry"
    required_ptype = "read"

    def execute(self, account=None, party_type=None, party=None,
                voucher_type=None, voucher_no=None, from_date=None,
                to_date=None, company=None, limit=50, **kwargs):
        frappe.has_permission("GL Entry", ptype="read", throw=True)

        limit = min(int(limit or 50), 200)
        filters = {"is_cancelled": 0}

        if company or self.company:
            filters["company"] = company or self.company
        if account:
            filters["account"] = ["like", f"%{account}%"]
        if party_type:
            filters["party_type"] = party_type
        if party:
            filters["party"] = ["like", f"%{party}%"]
        if voucher_type:
            filters["voucher_type"] = voucher_type
        if voucher_no:
            filters["voucher_no"] = voucher_no
        if from_date:
            filters["posting_date"] = [">=", from_date]
        if to_date:
            # If both from and to are set, use between
            if from_date:
                filters["posting_date"] = ["between", [from_date, to_date]]
            else:
                filters["posting_date"] = ["<=", to_date]

        entries = frappe.get_all(
            "GL Entry",
            filters=filters,
            fields=[
                "name",
                "posting_date",
                "account",
                "party_type",
                "party",
                "voucher_type",
                "voucher_no",
                "debit",
                "credit",
                "remarks",
            ],
            order_by="posting_date desc, creation desc",
            limit_page_length=limit,
        )

        total_debit = sum(e.get("debit") or 0 for e in entries)
        total_credit = sum(e.get("credit") or 0 for e in entries)

        return {
            "entries": entries,
            "count": len(entries),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "net": total_debit - total_credit,
        }
