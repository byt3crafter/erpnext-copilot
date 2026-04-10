import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetRevenueSummaryTool(BaseTool):
    name = "sales.get_revenue_summary"
    description = (
        "Summarise revenue from submitted Sales Invoices over a date range. "
        "Returns total revenue, invoice count, and average invoice value. "
        "When no specific customer is given, also returns the top customers by revenue. "
        "Optionally scoped to a single company, customer, territory (branch/location), "
        "or warehouse. When a user asks about sales for a location or branch name "
        "(e.g. 'North Region'), pass that name as the territory parameter."
    )
    parameters = {
        "from_date": {
            "type": "string",
            "description": "Start of the reporting period in YYYY-MM-DD format.",
        },
        "to_date": {
            "type": "string",
            "description": "End of the reporting period in YYYY-MM-DD format.",
        },
        "company": {
            "type": "string",
            "description": "Limit results to this company. Omit to include all companies.",
        },
        "customer": {
            "type": "string",
            "description": "Limit results to a single customer. Omit for company-wide summary.",
        },
        "territory": {
            "type": "string",
            "description": (
                "Limit results to a territory (branch/location/area). "
                "Accepts a partial name — the tool will match territories "
                "containing this string (e.g. 'North' matches "
                "'North Region', 'North Branch'). "
                "Use this when the user asks about sales for a branch or location."
            ),
        },
        "warehouse": {
            "type": "string",
            "description": (
                "Limit results to invoices from a specific warehouse. "
                "Accepts a partial name — matches against set_warehouse."
            ),
        },
    }
    required_params = ["from_date", "to_date"]
    action_type = "Report"
    required_doctype = "Sales Invoice"
    required_ptype = "read"

    def execute(self, from_date, to_date, company=None, customer=None,
                territory=None, warehouse=None, **kwargs):
        frappe.has_permission("Sales Invoice", ptype="read", throw=True)

        filters = {
            "docstatus": 1,
            "is_return": 0,
            "posting_date": ["between", [from_date, to_date]],
        }
        # Only apply the default company filter when no territory or warehouse
        # is specified. Territories and warehouses may span multiple companies
        # (e.g. a branch may be under a separate company), so the
        # company filter would incorrectly return zero results.
        if company:
            filters["company"] = company
        elif self.company and not territory and not warehouse:
            filters["company"] = self.company
        if customer:
            filters["customer"] = customer

        # Territory filter: match territories containing the given string
        if territory:
            matching_territories = frappe.get_all(
                "Territory",
                filters={"name": ["like", f"%{territory}%"]},
                pluck="name",
            )
            if matching_territories:
                if len(matching_territories) == 1:
                    filters["territory"] = matching_territories[0]
                else:
                    filters["territory"] = ["in", matching_territories]
            else:
                # No matching territory — return empty result with hint
                return {
                    "summary": {
                        "from_date": from_date,
                        "to_date": to_date,
                        "total_revenue": 0,
                        "invoice_count": 0,
                        "average_invoice_value": 0,
                        "note": f"No territory found matching '{territory}'. "
                                "Available territories can be searched with "
                                "core_get_list doctype=Territory.",
                    }
                }

        # Warehouse filter: match set_warehouse containing the given string
        if warehouse:
            filters["set_warehouse"] = ["like", f"%{warehouse}%"]

        invoices = frappe.get_all(
            "Sales Invoice",
            filters=filters,
            fields=["name", "customer", "grand_total", "posting_date", "territory",
                     "set_warehouse"],
        )

        total_revenue = sum(inv.get("grand_total") or 0.0 for inv in invoices)
        invoice_count = len(invoices)
        average_invoice_value = total_revenue / invoice_count if invoice_count else 0.0

        summary = {
            "from_date": from_date,
            "to_date": to_date,
            "total_revenue": total_revenue,
            "invoice_count": invoice_count,
            "average_invoice_value": average_invoice_value,
        }
        if territory:
            summary["territory_filter"] = territory
            if "territory" in filters:
                val = filters["territory"]
                summary["territories_matched"] = (
                    val if isinstance(val, str)
                    else val[1] if isinstance(val, list) and len(val) == 2
                    else str(val)
                )
        if warehouse:
            summary["warehouse_filter"] = warehouse

        if not customer:
            # Aggregate per customer for top-customers ranking
            customer_totals: dict = {}
            for inv in invoices:
                cust = inv.get("customer") or "Unknown"
                customer_totals[cust] = customer_totals.get(cust, 0.0) + (inv.get("grand_total") or 0.0)

            top_customers = sorted(
                [{"customer": c, "revenue": v} for c, v in customer_totals.items()],
                key=lambda x: x["revenue"],
                reverse=True,
            )[:10]

            summary["top_customers"] = top_customers

        return {"summary": summary}
