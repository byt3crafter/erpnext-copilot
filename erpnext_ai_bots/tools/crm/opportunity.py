import frappe
from erpnext_ai_bots.tools.base import BaseTool


class OpportunityTool(BaseTool):
    name = "crm.manage_opportunity"
    description = (
        "Create or track opportunities (deals in the sales pipeline). "
        "Actions: 'create' (new opportunity), 'get' (by name), 'list' (with filters)."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "create, get, or list",
        },
        "opportunity_name": {
            "type": "string",
            "description": "Opportunity document name (for get)",
        },
        "opportunity_from": {
            "type": "string",
            "description": "Lead or Customer (the source party type — for create)",
        },
        "party_name": {
            "type": "string",
            "description": "Name of the Lead or Customer linked to this opportunity",
        },
        "opportunity_type": {
            "type": "string",
            "description": "Sales, Maintenance, or other type (for create)",
        },
        "status": {
            "type": "string",
            "description": "Open, Quotation, Converted, Lost, Closed (filter for list; set for update)",
        },
        "expected_closing": {
            "type": "string",
            "description": "Expected closing date in YYYY-MM-DD format (for create)",
        },
        "opportunity_amount": {
            "type": "number",
            "description": "Estimated deal value (for create)",
        },
        "limit": {
            "type": "integer",
            "description": "Max opportunities to return for list action (default 20)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Opportunity"
    required_ptype = "read"

    def execute(self, action, opportunity_name=None, opportunity_from=None,
                party_name=None, opportunity_type=None, status=None,
                expected_closing=None, opportunity_amount=None, limit=20, **kwargs):
        action = action.lower().strip()

        if action == "create":
            return self._create(
                opportunity_from, party_name, opportunity_type,
                expected_closing, opportunity_amount
            )
        elif action == "get":
            return self._get(opportunity_name)
        elif action == "list":
            return self._list(status, opportunity_from, party_name, limit)
        else:
            frappe.throw(f"Unknown action '{action}'. Valid actions are: create, get, list.")

    def _create(self, opportunity_from, party_name, opportunity_type,
                expected_closing, opportunity_amount):
        frappe.has_permission("Opportunity", ptype="create", throw=True)

        if not opportunity_from or not party_name:
            frappe.throw(
                "Both opportunity_from (Lead or Customer) and party_name are required."
            )

        doc_data = {
            "doctype": "Opportunity",
            "opportunity_from": opportunity_from,
            "party_name": party_name,
            "opportunity_type": opportunity_type or "Sales",
            "status": "Open",
        }
        if expected_closing:
            doc_data["expected_closing"] = expected_closing
        if opportunity_amount:
            doc_data["opportunity_amount"] = opportunity_amount

        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "party_name": party_name,
            "message": (
                f"Opportunity '{doc.name}' created for {opportunity_from} '{party_name}'. "
                "Please review and add items/notes from the ERPNext desk."
            ),
        }

    def _get(self, opportunity_name):
        frappe.has_permission("Opportunity", ptype="read", throw=True)

        if not opportunity_name:
            frappe.throw("opportunity_name is required to get an opportunity.")

        if not frappe.db.exists("Opportunity", opportunity_name):
            # Try partial match
            matches = frappe.get_all(
                "Opportunity",
                filters={"name": ["like", f"%{opportunity_name}%"]},
                fields=["name"],
                limit_page_length=5,
            )
            if not matches:
                return {"opportunity": None, "message": f"No opportunity found matching '{opportunity_name}'."}
            opportunity_name = matches[0]["name"]

        doc = frappe.get_doc("Opportunity", opportunity_name)
        return {
            "opportunity": {
                "name": doc.name,
                "opportunity_from": doc.opportunity_from,
                "party_name": doc.party_name,
                "opportunity_type": doc.opportunity_type,
                "status": doc.status,
                "expected_closing": str(doc.expected_closing) if doc.expected_closing else None,
                "opportunity_amount": doc.opportunity_amount,
                "contact_email": doc.contact_email,
                "creation": str(doc.creation),
            }
        }

    def _list(self, status, opportunity_from, party_name, limit):
        frappe.has_permission("Opportunity", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}
        if status:
            filters["status"] = status
        if opportunity_from:
            filters["opportunity_from"] = opportunity_from
        if party_name:
            filters["party_name"] = ["like", f"%{party_name}%"]

        opportunities = frappe.get_all(
            "Opportunity",
            filters=filters,
            fields=[
                "name",
                "opportunity_from",
                "party_name",
                "opportunity_type",
                "status",
                "expected_closing",
                "opportunity_amount",
                "creation",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )
        return {"opportunities": opportunities, "count": len(opportunities)}
