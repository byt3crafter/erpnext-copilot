import frappe
from erpnext_ai_bots.tools.base import BaseTool


_STATUS_DOCSTATUS_MAP = {
    "Draft": 0,
    "Unpaid": 1,
    "Paid": 1,
    "Overdue": 1,
    "Cancelled": 2,
}

_OVERDUE_STATUSES = {"Overdue"}


class GetPurchaseInvoicesTool(BaseTool):
    name = "purchase.get_purchase_invoices"
    description = (
        "Get purchase invoices with filters. "
        "Useful for checking what is owed to suppliers, overdue bills, or payment history."
    )
    parameters = {
        "supplier": {
            "type": "string",
            "description": "Supplier name to filter by (optional)",
        },
        "from_date": {
            "type": "string",
            "description": "Start posting date in YYYY-MM-DD format (optional)",
        },
        "to_date": {
            "type": "string",
            "description": "End posting date in YYYY-MM-DD format (optional)",
        },
        "status": {
            "type": "string",
            "description": "Draft, Unpaid, Overdue, Paid, or Cancelled (optional)",
        },
        "company": {
            "type": "string",
            "description": "Company name (optional, defaults to session company)",
        },
        "limit": {
            "type": "integer",
            "description": "Max invoices to return (default 20, max 100)",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Purchase Invoice"
    required_ptype = "read"

    def execute(self, supplier=None, from_date=None, to_date=None,
                status=None, company=None, limit=20, **kwargs):
        frappe.has_permission("Purchase Invoice", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}

        if company or self.company:
            filters["company"] = company or self.company
        if supplier:
            filters["supplier"] = ["like", f"%{supplier}%"]
        if from_date and to_date:
            filters["posting_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_date"] = [">=", from_date]
        elif to_date:
            filters["posting_date"] = ["<=", to_date]

        # Map status to docstatus and extra filters
        if status:
            docstatus = _STATUS_DOCSTATUS_MAP.get(status)
            if docstatus is not None:
                filters["docstatus"] = docstatus
            if status == "Unpaid":
                filters["outstanding_amount"] = [">", 0]
            elif status == "Paid":
                filters["outstanding_amount"] = ["<=", 0]
                filters["docstatus"] = 1
            elif status == "Overdue":
                filters["outstanding_amount"] = [">", 0]
                filters["due_date"] = ["<", frappe.utils.today()]
                filters["docstatus"] = 1

        invoices = frappe.get_all(
            "Purchase Invoice",
            filters=filters,
            fields=[
                "name",
                "supplier",
                "supplier_name",
                "posting_date",
                "due_date",
                "grand_total",
                "outstanding_amount",
                "status",
                "bill_no",
            ],
            order_by="posting_date desc",
            limit_page_length=limit,
        )

        total_outstanding = sum(i.get("outstanding_amount") or 0 for i in invoices)
        total_amount = sum(i.get("grand_total") or 0 for i in invoices)

        return {
            "invoices": invoices,
            "count": len(invoices),
            "total_amount": total_amount,
            "total_outstanding": total_outstanding,
        }
