import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateLeaveApplicationTool(BaseTool):
    name = "hr.create_leave_application"
    description = (
        "Create a draft Leave Application for an employee. "
        "The application is saved but not submitted — the user must confirm before it is submitted."
    )
    parameters = {
        "employee": {
            "type": "string",
            "description": "Employee ID (e.g. 'EMP-0001').",
        },
        "leave_type": {
            "type": "string",
            "description": "Type of leave, e.g. 'Annual Leave', 'Sick Leave'.",
        },
        "from_date": {
            "type": "string",
            "description": "Start date of the leave in YYYY-MM-DD format.",
        },
        "to_date": {
            "type": "string",
            "description": "End date of the leave in YYYY-MM-DD format.",
        },
        "reason": {
            "type": "string",
            "description": "Optional reason or description for the leave request.",
        },
    }
    required_params = ["employee", "leave_type", "from_date", "to_date"]
    action_type = "Create"
    required_doctype = "Leave Application"
    required_ptype = "create"

    def execute(self, employee, leave_type, from_date, to_date, reason=None, **kwargs):
        frappe.has_permission("Leave Application", ptype="create", throw=True)

        values = {
            "doctype": "Leave Application",
            "employee": employee,
            "leave_type": leave_type,
            "from_date": from_date,
            "to_date": to_date,
            "status": "Open",
        }
        if reason:
            values["description"] = reason

        doc = frappe.get_doc(values)
        doc.insert()

        return {
            "status": "created",
            "name": doc.name,
            "employee": doc.employee,
            "leave_type": doc.leave_type,
            "from_date": str(doc.from_date),
            "to_date": str(doc.to_date),
            "total_leave_days": doc.total_leave_days,
            "message": (
                f"Draft Leave Application '{doc.name}' created for {employee} "
                f"({leave_type}, {from_date} to {to_date}). "
                "Ask the user to confirm before submitting."
            ),
        }
