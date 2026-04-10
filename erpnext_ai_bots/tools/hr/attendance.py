import frappe
from erpnext_ai_bots.tools.base import BaseTool


_KNOWN_STATUSES = ("Present", "Absent", "Half Day", "On Leave", "Work From Home")


class GetAttendanceSummaryTool(BaseTool):
    name = "hr.get_attendance_summary"
    description = (
        "Get an attendance summary for an employee over a date range. "
        "Returns a count breakdown by status (Present, Absent, Half Day, On Leave, etc.) "
        "and the total number of working days in the range. "
        "If no employee is given, resolves the caller's employee record."
    )
    parameters = {
        "employee": {
            "type": "string",
            "description": "Employee ID (e.g. 'EMP-0001'). Defaults to the logged-in user's employee record.",
        },
        "from_date": {
            "type": "string",
            "description": "Start of the date range in YYYY-MM-DD format.",
        },
        "to_date": {
            "type": "string",
            "description": "End of the date range in YYYY-MM-DD format.",
        },
    }
    required_params = ["from_date", "to_date"]
    action_type = "Read"
    required_doctype = "Attendance"
    required_ptype = "read"

    def _resolve_employee(self, employee: str | None) -> str:
        if employee:
            return employee
        emp = frappe.db.get_value("Employee", {"user_id": self.user}, "name")
        if not emp:
            frappe.throw(
                f"No Employee record linked to user '{self.user}'. "
                "Please provide an employee ID explicitly."
            )
        return emp

    def execute(self, from_date, to_date, employee=None, **kwargs):
        frappe.has_permission("Attendance", ptype="read", throw=True)

        employee = self._resolve_employee(employee)

        records = frappe.get_all(
            "Attendance",
            filters={
                "employee": employee,
                "attendance_date": ["between", [from_date, to_date]],
                "docstatus": 1,
            },
            fields=["attendance_date", "status"],
            order_by="attendance_date asc",
            limit_page_length=0,
        )

        # Build summary counts; include all known statuses even when zero
        summary: dict[str, int] = {s: 0 for s in _KNOWN_STATUSES}
        for row in records:
            status = row["status"]
            summary[status] = summary.get(status, 0) + 1

        # Drop zero-count statuses that aren't in the canonical list (dynamic statuses present in data)
        for row in records:
            status = row["status"]
            if status not in summary:
                summary[status] = 1

        # Remove canonical statuses that have zero count to keep the response lean,
        # but only if they were never observed in actual data
        observed_statuses = {row["status"] for row in records}
        cleaned_summary = {
            status: count
            for status, count in summary.items()
            if count > 0 or status in observed_statuses
        }

        return {
            "employee": employee,
            "from_date": from_date,
            "to_date": to_date,
            "total_records": len(records),
            "summary": cleaned_summary,
        }
