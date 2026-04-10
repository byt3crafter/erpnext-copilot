import frappe
from erpnext_ai_bots.tools.base import BaseTool


# Fields that are safe to surface. Bank details, emergency contact numbers,
# health insurance IDs, and any internally sensitive identifiers are excluded.
_SAFE_FIELDS = [
    "name",
    "employee_name",
    "status",
    "company",
    "department",
    "designation",
    "employment_type",
    "date_of_joining",
    "date_of_birth",
    "gender",
    "branch",
    "reports_to",
    "user_id",
    "cell_number",
    "personal_email",
    "company_email",
    "prefered_contact_email",
    "image",
    "holiday_list",
    "leave_approver",
    "expense_approver",
    "salary_currency",
    "notice_number_of_days",
    "relieving_date",
    "reason_for_leaving",
    "contracts",
]


class GetEmployeeInfoTool(BaseTool):
    name = "hr.get_employee_info"
    description = (
        "Fetch employee information. Provide an employee ID or employee name to look up a specific "
        "person, or pass filters to search across multiple employees. "
        "Returns a curated set of safe fields — bank details and sensitive personal data are excluded."
    )
    parameters = {
        "employee": {
            "type": "string",
            "description": (
                "Employee ID (e.g. 'EMP-0001') or full employee name. "
                "When provided, a direct document lookup is performed."
            ),
        },
        "filters": {
            "type": "object",
            "description": (
                "Frappe-style filter dict for searching multiple employees, "
                "e.g. {'department': 'Engineering', 'status': 'Active'}. "
                "Used only when 'employee' is not given."
            ),
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Employee"
    required_ptype = "read"

    def _doc_to_safe_dict(self, doc) -> dict:
        return {field: doc.get(field) for field in _SAFE_FIELDS if doc.get(field) is not None}

    def execute(self, employee=None, filters=None, **kwargs):
        frappe.has_permission("Employee", ptype="read", throw=True)

        if employee:
            # The caller may pass a name like 'EMP-0001' or a full name like 'Jane Doe'.
            # Try a direct lookup first; fall back to employee_name search.
            if frappe.db.exists("Employee", employee):
                doc = frappe.get_doc("Employee", employee)
                frappe.has_permission("Employee", doc=doc, ptype="read", throw=True)
                return {"employee": self._doc_to_safe_dict(doc)}

            # Attempt match on employee_name (full-name search)
            matched = frappe.get_all(
                "Employee",
                filters={"employee_name": ["like", f"%{employee}%"]},
                fields=_SAFE_FIELDS,
                limit_page_length=10,
            )
            if not matched:
                frappe.throw(f"No Employee found matching '{employee}'.")
            if len(matched) == 1:
                return {"employee": matched[0]}
            return {"employees": matched, "count": len(matched), "message": "Multiple matches found."}

        # No specific employee — use caller-supplied filters or default to active employees
        search_filters = dict(filters) if filters else {"status": "Active"}
        if self.company:
            search_filters.setdefault("company", self.company)

        employees = frappe.get_all(
            "Employee",
            filters=search_filters,
            fields=_SAFE_FIELDS,
            order_by="employee_name asc",
            limit_page_length=50,
        )

        return {"employees": employees, "count": len(employees)}
