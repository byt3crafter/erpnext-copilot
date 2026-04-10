import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetSalesOrdersTool(BaseTool):
    name = "sales.get_sales_orders"
    description = (
        "List Sales Orders with optional filters for customer, status, and date range. "
        "Returns up to 50 orders with delivery and billing progress percentages."
    )
    parameters = {
        "customer": {
            "type": "string",
            "description": "Customer name to filter orders. Omit to return orders for all customers.",
        },
        "status": {
            "type": "string",
            "description": (
                "Sales Order status to filter by, e.g. 'Draft', 'To Deliver and Bill', "
                "'To Bill', 'To Deliver', 'Completed', 'Cancelled', 'Closed'. "
                "Omit to return all statuses."
            ),
        },
        "from_date": {
            "type": "string",
            "description": "Earliest transaction date to include, in YYYY-MM-DD format.",
        },
        "to_date": {
            "type": "string",
            "description": "Latest transaction date to include, in YYYY-MM-DD format.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Sales Order"
    required_ptype = "read"

    def execute(self, customer=None, status=None, from_date=None, to_date=None, **kwargs):
        frappe.has_permission("Sales Order", ptype="read", throw=True)

        filters = {}
        if customer:
            filters["customer"] = customer
        if status:
            filters["status"] = status
        if from_date:
            filters["transaction_date"] = [">=", from_date]
        if from_date and to_date:
            filters["transaction_date"] = ["between", [from_date, to_date]]
        elif to_date:
            filters["transaction_date"] = ["<=", to_date]

        orders = frappe.get_all(
            "Sales Order",
            filters=filters,
            fields=[
                "name",
                "customer",
                "transaction_date",
                "grand_total",
                "status",
                "per_delivered",
                "per_billed",
            ],
            order_by="transaction_date desc",
            limit_page_length=50,
        )

        return {
            "orders": orders,
            "count": len(orders),
        }
