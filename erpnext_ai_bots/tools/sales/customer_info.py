import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetCustomerInfoTool(BaseTool):
    name = "sales.get_customer_info"
    description = (
        "Look up a customer by name with smart fuzzy matching. "
        "Pass any part of the customer name or ID — the tool searches by exact match, "
        "partial match on customer_name, partial match on ID, and individual words. "
        "Returns full customer details including outstanding balance. "
        "If multiple matches are found, returns a list of close matches to choose from. "
        "Without a customer name, lists up to 20 customers optionally filtered by customer group. "
        "ALWAYS use this tool when looking for a customer — do NOT use core_get_list for customers."
    )
    parameters = {
        "customer": {
            "type": "string",
            "description": (
                "Customer document name or customer_name to look up. "
                "Omit to list customers (optionally narrowed by customer_group)."
            ),
        },
        "customer_group": {
            "type": "string",
            "description": (
                "Customer Group to filter the listing by, e.g. 'Commercial', 'Individual'. "
                "Only used when customer is not specified."
            ),
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Customer"
    required_ptype = "read"

    def _get_outstanding_amount(self, customer: str) -> float:
        """Sum outstanding_amount from submitted Sales Invoices for this customer."""
        result = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
            fields=["outstanding_amount"],
        )
        return sum(row.get("outstanding_amount") or 0.0 for row in result)

    def execute(self, customer=None, customer_group=None, **kwargs):
        frappe.has_permission("Customer", ptype="read", throw=True)

        if customer:
            # Try exact document name first, fall back to searching by customer_name
            if frappe.db.exists("Customer", customer):
                doc = frappe.get_doc("Customer", customer)
            else:
                # Try fuzzy match on customer_name first
                matches = frappe.get_all(
                    "Customer",
                    filters={"customer_name": ["like", f"%{customer}%"]},
                    fields=["name", "customer_name"],
                    limit_page_length=5,
                )
                # Also try matching on the document name (ID)
                if not matches:
                    matches = frappe.get_all(
                        "Customer",
                        filters={"name": ["like", f"%{customer}%"]},
                        fields=["name", "customer_name"],
                        limit_page_length=5,
                    )
                # Try each word separately if full string didn't match
                if not matches and " " in customer:
                    for word in customer.split():
                        if len(word) < 3:
                            continue
                        matches = frappe.get_all(
                            "Customer",
                            filters=[
                                ["customer_name", "like", f"%{word}%"],
                            ],
                            fields=["name", "customer_name"],
                            limit_page_length=5,
                        )
                        if not matches:
                            matches = frappe.get_all(
                                "Customer",
                                filters=[
                                    ["name", "like", f"%{word}%"],
                                ],
                                fields=["name", "customer_name"],
                                limit_page_length=5,
                            )
                        if matches:
                            break
                if not matches:
                    return {"customer": None, "message": f"No customer found matching '{customer}'. Try a different name or spelling."}
                if len(matches) > 1:
                    return {
                        "customer": None,
                        "close_matches": [{"id": m["name"], "name": m.get("customer_name", m["name"])} for m in matches],
                        "message": f"Multiple customers match '{customer}'. Which one did you mean?",
                    }
                doc = frappe.get_doc("Customer", matches[0]["name"])

            outstanding_amount = self._get_outstanding_amount(doc.name)

            return {
                "customer": {
                    "name": doc.name,
                    "customer_name": doc.customer_name,
                    "customer_group": doc.customer_group,
                    "territory": doc.territory,
                    "customer_type": doc.customer_type,
                    "default_currency": doc.default_currency,
                    "mobile_no": doc.mobile_no,
                    "email_id": doc.email_id,
                    "outstanding_amount": outstanding_amount,
                },
            }

        # List mode
        filters = {}
        if customer_group:
            filters["customer_group"] = customer_group

        customers = frappe.get_all(
            "Customer",
            filters=filters,
            fields=[
                "name",
                "customer_name",
                "customer_group",
                "territory",
                "customer_type",
            ],
            order_by="customer_name asc",
            limit_page_length=20,
        )

        return {
            "customers": customers,
            "count": len(customers),
        }
