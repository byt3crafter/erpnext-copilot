import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreatePaymentEntryTool(BaseTool):
    name = "accounting.create_payment_entry"
    description = (
        "Create a payment entry to record payments received from customers or paid to suppliers. "
        "Creates a draft — user must review and submit from ERPNext desk."
    )
    parameters = {
        "payment_type": {
            "type": "string",
            "description": "Receive (from customer) or Pay (to supplier)",
        },
        "party_type": {
            "type": "string",
            "description": "Customer or Supplier",
        },
        "party": {
            "type": "string",
            "description": "Customer or Supplier name exactly as stored in ERPNext",
        },
        "paid_amount": {
            "type": "number",
            "description": "Amount paid/received",
        },
        "reference_doctype": {
            "type": "string",
            "description": "Sales Invoice or Purchase Invoice (optional — to reconcile against)",
        },
        "reference_name": {
            "type": "string",
            "description": "Invoice number to reconcile against (optional)",
        },
        "mode_of_payment": {
            "type": "string",
            "description": "Cash, Bank Transfer, Cheque, etc.",
        },
        "company": {
            "type": "string",
            "description": "Company name. Defaults to the session company.",
        },
        "posting_date": {
            "type": "string",
            "description": "Posting date in YYYY-MM-DD format. Defaults to today.",
        },
    }
    required_params = ["payment_type", "party_type", "party", "paid_amount"]
    action_type = "Create"
    required_doctype = "Payment Entry"
    required_ptype = "create"

    def execute(self, payment_type, party_type, party, paid_amount,
                reference_doctype=None, reference_name=None,
                mode_of_payment=None, company=None, posting_date=None, **kwargs):
        frappe.has_permission("Payment Entry", ptype="create", throw=True)

        company = company or self.company
        posting_date = posting_date or frappe.utils.today()
        mode_of_payment = mode_of_payment or "Bank Transfer"

        # Resolve paid_to / paid_from accounts from company defaults
        company_doc = frappe.get_doc("Company", company)

        # Determine accounts based on payment_type
        if payment_type == "Receive":
            paid_from = (
                frappe.db.get_value("Account", {
                    "account_type": "Receivable",
                    "company": company,
                }, "name")
                or company_doc.default_receivable_account
            )
            paid_to = company_doc.default_cash_account or _get_default_bank(company)
        elif payment_type == "Pay":
            paid_from = company_doc.default_cash_account or _get_default_bank(company)
            paid_to = (
                frappe.db.get_value("Account", {
                    "account_type": "Payable",
                    "company": company,
                }, "name")
                or company_doc.default_payable_account
            )
        else:
            frappe.throw(
                f"Invalid payment_type '{payment_type}'. Must be 'Receive' or 'Pay'."
            )

        doc_data = {
            "doctype": "Payment Entry",
            "payment_type": payment_type,
            "posting_date": posting_date,
            "company": company,
            "mode_of_payment": mode_of_payment,
            "party_type": party_type,
            "party": party,
            "paid_amount": paid_amount,
            "received_amount": paid_amount,
            "paid_from": paid_from,
            "paid_to": paid_to,
        }

        # Attach invoice reference if provided
        if reference_doctype and reference_name:
            invoice = frappe.get_doc(reference_doctype, reference_name)
            doc_data["references"] = [{
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "total_amount": invoice.grand_total,
                "outstanding_amount": invoice.outstanding_amount,
                "allocated_amount": min(paid_amount, invoice.outstanding_amount),
            }]

        doc = frappe.get_doc(doc_data)
        doc.setup_party_account_field()
        doc.set_missing_values()
        doc.set_exchange_rate()
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "payment_type": payment_type,
            "party": party,
            "paid_amount": paid_amount,
            "message": (
                f"Draft Payment Entry '{doc.name}' created for {party_type} '{party}' "
                f"— amount {paid_amount:.2f}. Please review and submit from ERPNext desk."
            ),
        }


def _get_default_bank(company: str) -> str:
    """Return the first active bank account for the company."""
    result = frappe.get_all(
        "Bank Account",
        filters={"company": company, "is_default": 1},
        fields=["account"],
        limit_page_length=1,
    )
    if result:
        return result[0]["account"]
    result = frappe.get_all(
        "Bank Account",
        filters={"company": company},
        fields=["account"],
        limit_page_length=1,
    )
    return result[0]["account"] if result else None
