import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetLeaveBalanceTool(BaseTool):
    name = "hr.get_leave_balance"
    description = (
        "Get leave balances for an employee. Returns allocated, used, and remaining "
        "days per leave type. If no employee is given, resolves the caller's employee record."
    )
    parameters = {
        "employee": {
            "type": "string",
            "description": "Employee ID (e.g. 'EMP-0001'). Defaults to the logged-in user's employee record.",
        },
        "leave_type": {
            "type": "string",
            "description": "Filter to a specific leave type, e.g. 'Annual Leave'. Omit to get all types.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Leave Allocation"
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

    def execute(self, employee=None, leave_type=None, **kwargs):
        frappe.has_permission("Leave Allocation", ptype="read", throw=True)
        frappe.has_permission("Leave Application", ptype="read", throw=True)

        employee = self._resolve_employee(employee)

        allocation_filters = {"employee": employee, "docstatus": 1}
        if leave_type:
            allocation_filters["leave_type"] = leave_type

        allocations = frappe.get_all(
            "Leave Allocation",
            filters=allocation_filters,
            fields=["leave_type", "total_leaves_allocated", "from_date", "to_date"],
        )

        # Aggregate total allocated days per leave type across all active allocations
        allocated_by_type: dict[str, float] = {}
        for row in allocations:
            lt = row["leave_type"]
            allocated_by_type[lt] = allocated_by_type.get(lt, 0) + (row["total_leaves_allocated"] or 0)

        if not allocated_by_type:
            return {"employee": employee, "balances": [], "message": "No active leave allocations found."}

        # Fetch approved/open leave applications to compute used days
        application_filters = {
            "employee": employee,
            "docstatus": 1,
            "status": ["in", ["Approved", "Open"]],
        }
        if leave_type:
            application_filters["leave_type"] = leave_type

        applications = frappe.get_all(
            "Leave Application",
            filters=application_filters,
            fields=["leave_type", "total_leave_days"],
        )

        used_by_type: dict[str, float] = {}
        for row in applications:
            lt = row["leave_type"]
            used_by_type[lt] = used_by_type.get(lt, 0) + (row["total_leave_days"] or 0)

        balances = []
        for lt, allocated in allocated_by_type.items():
            used = used_by_type.get(lt, 0)
            balances.append(
                {
                    "leave_type": lt,
                    "allocated": allocated,
                    "used": used,
                    "remaining": allocated - used,
                }
            )

        balances.sort(key=lambda r: r["leave_type"])

        return {"employee": employee, "balances": balances}
