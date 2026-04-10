import frappe
from erpnext_ai_bots.tools.base import BaseTool


class IssueTool(BaseTool):
    name = "support.manage_issue"
    description = (
        "Create, update, or list support issues/tickets. "
        "Actions: 'create', 'update', 'get', 'list'."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "create, update, get, or list",
        },
        "issue_name": {
            "type": "string",
            "description": "Issue document name/ID (for get/update)",
        },
        "subject": {
            "type": "string",
            "description": "Issue title/subject (for create)",
        },
        "customer": {
            "type": "string",
            "description": "Customer linked to the issue (for create or list filter)",
        },
        "priority": {
            "type": "string",
            "description": "Low, Medium, High, or Urgent",
        },
        "status": {
            "type": "string",
            "description": "Open, Replied, Resolved, Closed (filter for list or set for update)",
        },
        "description": {
            "type": "string",
            "description": "Detailed description of the issue (for create/update)",
        },
        "raised_by": {
            "type": "string",
            "description": "Email of the person who raised the issue (for create)",
        },
        "limit": {
            "type": "integer",
            "description": "Max issues to return for list action (default 20)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Issue"
    required_ptype = "read"

    def execute(self, action, issue_name=None, subject=None, customer=None,
                priority=None, status=None, description=None, raised_by=None,
                limit=20, **kwargs):
        action = action.lower().strip()

        if action == "create":
            return self._create(subject, customer, priority, description, raised_by)
        elif action == "update":
            return self._update(issue_name, status, priority, description)
        elif action == "get":
            return self._get(issue_name)
        elif action == "list":
            return self._list(customer, status, priority, limit)
        else:
            frappe.throw(
                f"Unknown action '{action}'. Valid actions are: create, update, get, list."
            )

    def _create(self, subject, customer, priority, description, raised_by):
        frappe.has_permission("Issue", ptype="create", throw=True)

        if not subject:
            frappe.throw("subject is required to create an issue.")

        doc_data = {
            "doctype": "Issue",
            "subject": subject,
            "priority": priority or "Medium",
            "status": "Open",
        }
        if customer:
            doc_data["customer"] = customer
        if description:
            doc_data["description"] = description
        if raised_by:
            doc_data["raised_by"] = raised_by

        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "subject": doc.subject,
            "message": (
                f"Issue '{subject}' created as {doc.name} with {priority or 'Medium'} priority."
            ),
        }

    def _update(self, issue_name, status, priority, description):
        frappe.has_permission("Issue", ptype="write", throw=True)

        if not issue_name:
            frappe.throw("issue_name is required to update an issue.")

        doc = frappe.get_doc("Issue", issue_name)

        if status:
            doc.status = status
        if priority:
            doc.priority = priority
        if description:
            doc.description = description

        doc.save(ignore_permissions=False)

        return {
            "status": "updated",
            "name": doc.name,
            "subject": doc.subject,
            "message": f"Issue '{doc.name}' updated successfully.",
        }

    def _get(self, issue_name):
        frappe.has_permission("Issue", ptype="read", throw=True)

        if not issue_name:
            frappe.throw("issue_name is required to get an issue.")

        if not frappe.db.exists("Issue", issue_name):
            # Partial match on subject
            matches = frappe.get_all(
                "Issue",
                filters={"subject": ["like", f"%{issue_name}%"]},
                fields=["name", "subject"],
                limit_page_length=5,
            )
            if not matches:
                return {"issue": None, "message": f"No issue found matching '{issue_name}'."}
            issue_name = matches[0]["name"]

        doc = frappe.get_doc("Issue", issue_name)
        return {
            "issue": {
                "name": doc.name,
                "subject": doc.subject,
                "customer": doc.customer,
                "priority": doc.priority,
                "status": doc.status,
                "raised_by": doc.raised_by,
                "description": doc.description,
                "first_responded_on": str(doc.first_responded_on) if doc.first_responded_on else None,
                "resolution_date": str(doc.resolution_date) if doc.resolution_date else None,
                "creation": str(doc.creation),
            }
        }

    def _list(self, customer, status, priority, limit):
        frappe.has_permission("Issue", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}
        if customer:
            filters["customer"] = ["like", f"%{customer}%"]
        if status:
            filters["status"] = status
        if priority:
            filters["priority"] = priority

        issues = frappe.get_all(
            "Issue",
            filters=filters,
            fields=[
                "name",
                "subject",
                "customer",
                "priority",
                "status",
                "raised_by",
                "creation",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )
        return {"issues": issues, "count": len(issues)}
