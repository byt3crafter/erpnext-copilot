import frappe
from erpnext_ai_bots.tools.base import BaseTool


class TaskTool(BaseTool):
    name = "project.manage_task"
    description = (
        "Create, update, or list project tasks. "
        "Actions: 'create', 'update', 'get', 'list'."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "create, update, get, or list",
        },
        "task_name": {
            "type": "string",
            "description": "Task document name (for get/update)",
        },
        "project": {
            "type": "string",
            "description": "Project name this task belongs to (for create or list filter)",
        },
        "subject": {
            "type": "string",
            "description": "Task title/subject (for create)",
        },
        "status": {
            "type": "string",
            "description": "Open, Working, Pending Review, Overdue, Completed, Cancelled",
        },
        "assigned_to": {
            "type": "string",
            "description": "User email to assign the task to",
        },
        "priority": {
            "type": "string",
            "description": "Low, Medium, High, Urgent",
        },
        "description": {
            "type": "string",
            "description": "Task description or notes (for create/update)",
        },
        "exp_end_date": {
            "type": "string",
            "description": "Expected end/due date in YYYY-MM-DD format",
        },
        "limit": {
            "type": "integer",
            "description": "Max tasks to return for list action (default 30)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Task"
    required_ptype = "read"

    def execute(self, action, task_name=None, project=None, subject=None,
                status=None, assigned_to=None, priority=None, description=None,
                exp_end_date=None, limit=30, **kwargs):
        action = action.lower().strip()

        if action == "create":
            return self._create(project, subject, status, assigned_to, priority,
                                description, exp_end_date)
        elif action == "update":
            return self._update(task_name, status, assigned_to, priority,
                                description, exp_end_date)
        elif action == "get":
            return self._get(task_name)
        elif action == "list":
            return self._list(project, status, assigned_to, priority, limit)
        else:
            frappe.throw(
                f"Unknown action '{action}'. Valid actions are: create, update, get, list."
            )

    def _create(self, project, subject, status, assigned_to, priority,
                description, exp_end_date):
        frappe.has_permission("Task", ptype="create", throw=True)

        if not subject:
            frappe.throw("subject is required to create a task.")

        doc_data = {
            "doctype": "Task",
            "subject": subject,
            "status": status or "Open",
            "priority": priority or "Medium",
        }
        if project:
            doc_data["project"] = project
        if assigned_to:
            doc_data["assigned_to"] = [{"owner": assigned_to}]
        if description:
            doc_data["description"] = description
        if exp_end_date:
            doc_data["exp_end_date"] = exp_end_date

        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=False)

        return {
            "status": "created",
            "name": doc.name,
            "subject": doc.subject,
            "project": doc.project,
            "message": f"Task '{subject}' created as {doc.name}.",
        }

    def _update(self, task_name, status, assigned_to, priority, description, exp_end_date):
        frappe.has_permission("Task", ptype="write", throw=True)

        if not task_name:
            frappe.throw("task_name is required to update a task.")

        doc = frappe.get_doc("Task", task_name)

        if status:
            doc.status = status
        if priority:
            doc.priority = priority
        if description:
            doc.description = description
        if exp_end_date:
            doc.exp_end_date = exp_end_date
        if assigned_to:
            # Append to assignees if not already present
            existing = [a.owner for a in (doc.assigned_to or [])]
            if assigned_to not in existing:
                doc.append("assigned_to", {"owner": assigned_to})

        doc.save(ignore_permissions=False)

        return {
            "status": "updated",
            "name": doc.name,
            "subject": doc.subject,
            "message": f"Task '{doc.name}' updated successfully.",
        }

    def _get(self, task_name):
        frappe.has_permission("Task", ptype="read", throw=True)

        if not task_name:
            frappe.throw("task_name is required.")

        if not frappe.db.exists("Task", task_name):
            matches = frappe.get_all(
                "Task",
                filters={"subject": ["like", f"%{task_name}%"]},
                fields=["name", "subject"],
                limit_page_length=5,
            )
            if not matches:
                return {"task": None, "message": f"No task found matching '{task_name}'."}
            task_name = matches[0]["name"]

        doc = frappe.get_doc("Task", task_name)
        return {
            "task": {
                "name": doc.name,
                "subject": doc.subject,
                "project": doc.project,
                "status": doc.status,
                "priority": doc.priority,
                "assigned_to": [a.owner for a in (doc.assigned_to or [])],
                "description": doc.description,
                "exp_end_date": str(doc.exp_end_date) if doc.exp_end_date else None,
            }
        }

    def _list(self, project, status, assigned_to, priority, limit):
        frappe.has_permission("Task", ptype="read", throw=True)

        limit = min(int(limit or 30), 100)
        filters = {}
        if project:
            filters["project"] = project
        if status:
            filters["status"] = status
        if priority:
            filters["priority"] = priority

        tasks = frappe.get_all(
            "Task",
            filters=filters,
            fields=[
                "name",
                "subject",
                "project",
                "status",
                "priority",
                "exp_end_date",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )
        return {"tasks": tasks, "count": len(tasks)}
