import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetStockBalanceTool(BaseTool):
    name = "stock.get_stock_balance"
    description = (
        "Fetch the Stock Balance report for a company. "
        "Returns up to 50 rows showing actual quantity and valuation rate per item and warehouse. "
        "All parameters are optional — omit any to retrieve a broader result set."
    )
    parameters = {
        "item_code": {
            "type": "string",
            "description": "Exact item code to filter on. Omit to return all items.",
        },
        "warehouse": {
            "type": "string",
            "description": "Warehouse name to filter on. Omit to return all warehouses.",
        },
        "company": {
            "type": "string",
            "description": "Legal name of the company as stored in ERPNext. Defaults to the bot's active company.",
        },
    }
    required_params = []
    action_type = "Report"
    required_doctype = "Stock Ledger Entry"
    required_ptype = "read"

    def execute(self, item_code=None, warehouse=None, company=None, **kwargs):
        frappe.has_permission("Stock Ledger Entry", ptype="read", throw=True)

        filters = {
            "company": company or self.company,
        }
        if item_code:
            filters["item_code"] = item_code
        if warehouse:
            filters["warehouse"] = warehouse

        result = frappe.call(
            "frappe.desk.query_report.run",
            report_name="Stock Balance",
            filters=filters,
        )

        rows = result.get("result", [])

        # The report result may include a totals footer row (no item_code); skip it.
        data_rows = [r for r in rows if isinstance(r, dict) and r.get("item_code")]

        data = [
            {
                "item_code": r.get("item_code"),
                "warehouse": r.get("warehouse"),
                "actual_qty": r.get("bal_qty") or r.get("actual_qty") or 0,
                "valuation_rate": r.get("val_rate") or r.get("valuation_rate") or 0,
            }
            for r in data_rows[:50]
        ]

        return {
            "data": data,
            "total_rows": len(data_rows),
            "showing": len(data),
            "filters_applied": filters,
        }
