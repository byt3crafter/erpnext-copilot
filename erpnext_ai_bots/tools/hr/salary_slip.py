import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetSalarySlipTool(BaseTool):
    name = "hr.get_salary_slip"
    description = (
        "Retrieve salary slips for an employee, optionally filtered by month and year. "
        "Returns key payroll fields: gross pay, net pay, deductions, and posting date. "
        "If no employee is given, resolves the caller's employee record."
    )
    parameters = {
        "employee": {
            "type": "string",
            "description": "Employee ID (e.g. 'EMP-0001'). Defaults to the logged-in user's employee record.",
        },
        "month": {
            "type": "integer",
            "description": "Calendar month (1–12) to filter by.",
        },
        "year": {
            "type": "integer",
            "description": "Calendar year (e.g. 2025) to filter by.",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Salary Slip"
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

    def execute(self, employee=None, month=None, year=None, **kwargs):
        frappe.has_permission("Salary Slip", ptype="read", throw=True)

        employee = self._resolve_employee(employee)

        filters: dict = {"employee": employee, "docstatus": 1}

        if year and month:
            # posting_date falls within the requested month
            import datetime
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            filters["posting_date"] = [
                "between",
                [
                    datetime.date(year, month, 1).isoformat(),
                    datetime.date(year, month, last_day).isoformat(),
                ],
            ]
        elif year:
            import datetime
            filters["posting_date"] = [
                "between",
                [
                    datetime.date(year, 1, 1).isoformat(),
                    datetime.date(year, 12, 31).isoformat(),
                ],
            ]

        slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "posting_date",
                "start_date",
                "end_date",
                "gross_pay",
                "total_deduction",
                "net_pay",
                "currency",
                "salary_structure",
                "company",
            ],
            order_by="posting_date desc",
            limit_page_length=24,
        )

        return {"employee": employee, "salary_slips": slips, "count": len(slips)}
