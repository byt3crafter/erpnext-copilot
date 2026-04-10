import frappe
from erpnext_ai_bots.tools.base import BaseTool


class LeadTool(BaseTool):
    name = "crm.manage_lead"
    description = (
        "Create or look up leads. "
        "Actions: 'create' (new lead), 'get' (by name/email), 'list' (with filters)."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "create, get, or list",
        },
        "lead_name": {
            "type": "string",
            "description": "Lead document name (for get) or full name of the contact (for create)",
        },
        "email": {
            "type": "string",
            "description": "Email address of the lead (for create or search)",
        },
        "phone": {
            "type": "string",
            "description": "Phone number (for create)",
        },
        "company_name": {
            "type": "string",
            "description": "Company the lead belongs to (for create or list filter)",
        },
        "source": {
            "type": "string",
            "description": "Lead source e.g. Cold Calling, Advertisement, Campaign (for create)",
        },
        "status": {
            "type": "string",
            "description": "Lead status filter for list: Open, Replied, Opportunity, etc.",
        },
        "limit": {
            "type": "integer",
            "description": "Max leads to return for list action (default 20)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Lead"
    required_ptype = "read"

    def execute(self, action, lead_name=None, email=None, phone=None,
                company_name=None, source=None, status=None, limit=20, **kwargs):
        action = action.lower().strip()

        if action == "create":
            return self._create(lead_name, email, phone, company_name, source)
        elif action == "get":
            return self._get(lead_name, email)
        elif action == "list":
            return self._list(status, company_name, limit)
        else:
            frappe.throw(f"Unknown action '{action}'. Valid actions are: create, get, list.")

    def _create(self, lead_name, email, phone, company_name, source):
        frappe.has_permission("Lead", ptype="create", throw=True)

        if not lead_name:
            frappe.throw("lead_name (contact's full name) is required to create a lead.")

        doc = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": lead_name,
            "email_id": email or "",
            "mobile_no": phone or "",
            "company_name": company_name or "",
            "source": source or "",
        })
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "lead_name": doc.lead_name,
            "message": f"Lead '{lead_name}' created as {doc.name}.",
        }

    def _get(self, lead_name, email):
        frappe.has_permission("Lead", ptype="read", throw=True)

        if not lead_name and not email:
            frappe.throw("Provide lead_name or email to look up a lead.")

        # Exact doc name
        if lead_name and frappe.db.exists("Lead", lead_name):
            doc = frappe.get_doc("Lead", lead_name)
            return {"lead": self._to_dict(doc)}

        # Search by name/email
        filters = []
        if lead_name:
            filters.append(["lead_name", "like", f"%{lead_name}%"])
        if email:
            filters.append(["email_id", "=", email])

        matches = frappe.get_all(
            "Lead",
            filters=filters,
            fields=["name", "lead_name", "email_id"],
            limit_page_length=5,
        )

        if not matches:
            return {"lead": None, "message": "No lead found matching those details."}
        if len(matches) > 1:
            return {
                "lead": None,
                "close_matches": [
                    {"id": m["name"], "name": m["lead_name"], "email": m["email_id"]}
                    for m in matches
                ],
                "message": "Multiple leads match. Which one did you mean?",
            }

        doc = frappe.get_doc("Lead", matches[0]["name"])
        return {"lead": self._to_dict(doc)}

    def _list(self, status, company_name, limit):
        frappe.has_permission("Lead", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}
        if status:
            filters["status"] = status
        if company_name:
            filters["company_name"] = ["like", f"%{company_name}%"]

        leads = frappe.get_all(
            "Lead",
            filters=filters,
            fields=[
                "name",
                "lead_name",
                "company_name",
                "email_id",
                "mobile_no",
                "status",
                "source",
                "creation",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )
        return {"leads": leads, "count": len(leads)}

    def _to_dict(self, doc) -> dict:
        return {
            "name": doc.name,
            "lead_name": doc.lead_name,
            "company_name": doc.company_name,
            "email_id": doc.email_id,
            "mobile_no": doc.mobile_no,
            "status": doc.status,
            "source": doc.source,
            "lead_owner": doc.lead_owner,
            "creation": str(doc.creation),
        }
