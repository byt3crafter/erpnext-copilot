import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetOutstandingInvoicesTool(BaseTool):
    name = "accounting.get_outstanding_invoices"
    description = (
        "List submitted Sales Invoices or Purchase Invoices that still have an outstanding amount. "
        "Optionally filter by a specific party (customer or supplier). "
        "Returns the invoice list, count, and total outstanding balance."
    )
    parameters = {
        "invoice_type": {
            "type": "string",
            "enum": ["Sales Invoice", "Purchase Invoice"],
            "description": "Type of invoice to query.",
        },
        "party": {
            "type": "string",
            "description": (
                "Customer name (for Sales Invoice) or Supplier name (for Purchase Invoice) "
                "to narrow results. Omit to fetch all parties."
            ),
        },
    }
    required_params = ["invoice_type"]
    action_type = "Read"
    required_doctype = "Sales Invoice"
    required_ptype = "read"

    def execute(self, invoice_type, party=None, **kwargs):
        frappe.has_permission(invoice_type, ptype="read", throw=True)

        party_field = "customer" if invoice_type == "Sales Invoice" else "supplier"

        filters = {
            "docstatus": 1,
            "outstanding_amount": [">", 0],
        }
        if party:
            filters[party_field] = party

        invoices = frappe.get_all(
            invoice_type,
            filters=filters,
            fields=[
                "name",
                "posting_date",
                party_field,
                "grand_total",
                "outstanding_amount",
                "currency",
                "due_date",
            ],
            order_by="due_date asc",
            limit_page_length=100,
        )

        total_outstanding = sum(inv.get("outstanding_amount", 0) or 0 for inv in invoices)

        return {
            "invoice_type": invoice_type,
            "invoices": invoices,
            "count": len(invoices),
            "total_outstanding": total_outstanding,
        }
