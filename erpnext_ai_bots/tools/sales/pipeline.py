import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetPipelineTool(BaseTool):
    name = "sales.get_pipeline"
    description = (
        "Fetch the sales pipeline from open Opportunities. "
        "Optionally filter by opportunity status or sales person. "
        "Returns each opportunity's key fields plus a summary of count per status "
        "and total pipeline value."
    )
    parameters = {
        "status": {
            "type": "string",
            "description": (
                "Filter opportunities by status, e.g. 'Open', 'Quotation', "
                "'Converted', 'Lost'. Omit to return all statuses."
            ),
        },
        "sales_person": {
            "type": "string",
            "description": (
                "Full name of the sales person as stored in ERPNext. "
                "Omit to return opportunities for all sales persons."
            ),
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Opportunity"
    required_ptype = "read"

    def execute(self, status=None, sales_person=None, **kwargs):
        frappe.has_permission("Opportunity", ptype="read", throw=True)

        filters = {}
        if status:
            filters["status"] = status
        if sales_person:
            filters["sales_person"] = sales_person

        opportunities = frappe.get_all(
            "Opportunity",
            filters=filters,
            fields=[
                "name",
                "opportunity_from",
                "party_name",
                "opportunity_amount",
                "status",
                "expected_closing",
            ],
            order_by="expected_closing asc",
        )

        status_counts: dict = {}
        total_pipeline_value = 0.0
        for opp in opportunities:
            opp_status = opp.get("status") or "Unknown"
            status_counts[opp_status] = status_counts.get(opp_status, 0) + 1
            total_pipeline_value += opp.get("opportunity_amount") or 0.0

        return {
            "opportunities": opportunities,
            "count": len(opportunities),
            "summary": {
                "count_by_status": status_counts,
                "total_pipeline_value": total_pipeline_value,
            },
        }
