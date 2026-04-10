import frappe
from erpnext_ai_bots.tools.base import BaseTool


class ProjectTool(BaseTool):
    name = "project.manage_project"
    description = (
        "Create, list, or get project details. "
        "Shows tasks, progress, and timelines. "
        "Actions: 'create', 'get', 'list'."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "create, get, or list",
        },
        "project_name": {
            "type": "string",
            "description": "Project name or document name (for get) or display name (for create)",
        },
        "status": {
            "type": "string",
            "description": "Open, Completed, Cancelled, Overdue (filter for list or set for create)",
        },
        "company": {
            "type": "string",
            "description": "Company name (optional, defaults to session company)",
        },
        "expected_start_date": {
            "type": "string",
            "description": "Expected project start date in YYYY-MM-DD format (for create)",
        },
        "expected_end_date": {
            "type": "string",
            "description": "Expected project end date in YYYY-MM-DD format (for create)",
        },
        "customer": {
            "type": "string",
            "description": "Customer linked to the project (optional)",
        },
        "limit": {
            "type": "integer",
            "description": "Max projects to return for list action (default 20)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Project"
    required_ptype = "read"

    def execute(self, action, project_name=None, status=None, company=None,
                expected_start_date=None, expected_end_date=None,
                customer=None, limit=20, **kwargs):
        action = action.lower().strip()

        if action == "create":
            return self._create(
                project_name, status, company, expected_start_date,
                expected_end_date, customer
            )
        elif action == "get":
            return self._get(project_name)
        elif action == "list":
            return self._list(status, company, customer, limit)
        else:
            frappe.throw(f"Unknown action '{action}'. Valid actions are: create, get, list.")

    def _create(self, project_name, status, company, expected_start_date,
                expected_end_date, customer):
        frappe.has_permission("Project", ptype="create", throw=True)

        if not project_name:
            frappe.throw("project_name is required to create a project.")

        doc_data = {
            "doctype": "Project",
            "project_name": project_name,
            "status": status or "Open",
            "company": company or self.company,
        }
        if expected_start_date:
            doc_data["expected_start_date"] = expected_start_date
        if expected_end_date:
            doc_data["expected_end_date"] = expected_end_date
        if customer:
            doc_data["customer"] = customer

        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "project_name": doc.project_name,
            "message": f"Project '{project_name}' created as {doc.name}.",
        }

    def _get(self, project_name):
        frappe.has_permission("Project", ptype="read", throw=True)

        if not project_name:
            frappe.throw("project_name is required to get a project.")

        if not frappe.db.exists("Project", project_name):
            matches = frappe.get_all(
                "Project",
                filters={"project_name": ["like", f"%{project_name}%"]},
                fields=["name", "project_name"],
                limit_page_length=5,
            )
            if not matches:
                matches = frappe.get_all(
                    "Project",
                    filters={"name": ["like", f"%{project_name}%"]},
                    fields=["name", "project_name"],
                    limit_page_length=5,
                )
            if not matches:
                return {"project": None, "message": f"No project found matching '{project_name}'."}
            project_name = matches[0]["name"]

        doc = frappe.get_doc("Project", project_name)

        # Fetch tasks summary
        tasks = frappe.get_all(
            "Task",
            filters={"project": doc.name},
            fields=["name", "subject", "status", "priority", "assigned_to", "exp_end_date"],
            order_by="creation asc",
            limit_page_length=50,
        )

        return {
            "project": {
                "name": doc.name,
                "project_name": doc.project_name,
                "status": doc.status,
                "company": doc.company,
                "customer": doc.customer,
                "percent_complete": doc.percent_complete,
                "expected_start_date": str(doc.expected_start_date) if doc.expected_start_date else None,
                "expected_end_date": str(doc.expected_end_date) if doc.expected_end_date else None,
                "tasks": tasks,
                "task_count": len(tasks),
            }
        }

    def _list(self, status, company, customer, limit):
        frappe.has_permission("Project", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}
        if status:
            filters["status"] = status
        if company or self.company:
            filters["company"] = company or self.company
        if customer:
            filters["customer"] = ["like", f"%{customer}%"]

        projects = frappe.get_all(
            "Project",
            filters=filters,
            fields=[
                "name",
                "project_name",
                "status",
                "company",
                "customer",
                "percent_complete",
                "expected_start_date",
                "expected_end_date",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )
        return {"projects": projects, "count": len(projects)}
