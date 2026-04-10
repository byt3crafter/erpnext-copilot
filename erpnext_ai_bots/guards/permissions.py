import frappe
from frappe import _

# Map namespaced tool names to (permission_type, fixed_doctype_or_None)
TOOL_PERMISSION_MAP = {
    "core.get_document": ("read", None),
    "core.get_list": ("read", None),
    "core.create_document": ("create", None),
    "core.update_document": ("write", None),
    "core.submit_document": ("submit", None),
    "core.run_report": ("read", None),
    "core.raw_sql": (None, None),   # SQL queries use DB-level auth, not DocType permissions
    "core.frappe_api": ("read", None),
    "core.send_email": (None, None),
    "core.send_report_email": (None, None),
    "core.analyze_image": (None, None),
    "core.read_file": (None, None),

    "accounting.get_trial_balance": ("read", "Account"),
    "accounting.get_outstanding_invoices": ("read", "Sales Invoice"),
    "accounting.get_bank_balances": ("read", "Bank Account"),
    "accounting.get_profit_and_loss": ("read", "Account"),
    "accounting.create_journal_entry": ("create", "Journal Entry"),
    "accounting.get_account_balance": ("read", "Account"),

    "hr.get_leave_balance": ("read", "Leave Allocation"),
    "hr.create_leave_application": ("create", "Leave Application"),
    "hr.get_salary_slip": ("read", "Salary Slip"),
    "hr.get_attendance_summary": ("read", "Attendance"),
    "hr.get_employee_info": ("read", "Employee"),

    "stock.get_stock_balance": ("read", "Stock Ledger Entry"),
    "stock.create_stock_entry": ("create", "Stock Entry"),
    "stock.get_warehouse_summary": ("read", "Warehouse"),
    "stock.get_item_info": ("read", "Item"),
    "stock.get_reorder_levels": ("read", "Item"),
    "stock.create_item": ("create", "Item"),
    "stock.get_inventory_days": ("read", "Stock Ledger Entry"),
    "stock.get_stock_turnover": ("read", "Stock Ledger Entry"),

    "sales.get_pipeline": ("read", "Opportunity"),
    "sales.create_quotation": ("create", "Quotation"),
    "sales.get_sales_orders": ("read", "Sales Order"),
    "sales.get_customer_info": ("read", "Customer"),
    "sales.get_revenue_summary": ("read", "Sales Invoice"),
    "sales.create_customer": ("create", "Customer"),
    "sales.get_branch_performance": ("read", "Sales Invoice"),
    "sales.get_sales_dashboard": ("read", "Sales Invoice"),

    "meta.spawn_subagent": (None, None),
    "meta.schedule_task": (None, None),
    "meta.saved_report": (None, None),  # Owner-scoped, no DocType permission check here

    # Accounting (extended)
    "accounting.create_payment_entry": ("create", "Payment Entry"),
    "accounting.get_general_ledger": ("read", "GL Entry"),
    "accounting.get_gross_margin": ("read", "Sales Invoice"),

    # Purchase tools
    "purchase.create_purchase_order": ("create", "Purchase Order"),
    "purchase.get_supplier_info": ("read", "Supplier"),
    "purchase.get_purchase_invoices": ("read", "Purchase Invoice"),
    "purchase.create_supplier": ("create", "Supplier"),

    # CRM tools
    "crm.manage_lead": ("read", "Lead"),
    "crm.manage_opportunity": ("read", "Opportunity"),

    # Project tools
    "project.manage_project": ("read", "Project"),
    "project.manage_task": ("read", "Task"),

    # Support tools
    "support.manage_issue": ("read", "Issue"),

    # Asset tools
    "asset.manage_asset": ("read", "Asset"),
}


# Tools restricted to management roles (require at least one of these roles)
MANAGEMENT_ROLES = {"System Manager", "Accounts Manager", "Sales Manager", "Stock Manager"}
ROLE_RESTRICTED_TOOLS = {
    "accounting.get_gross_margin": MANAGEMENT_ROLES,
    "sales.get_branch_performance": MANAGEMENT_ROLES,
    "sales.get_sales_dashboard": MANAGEMENT_ROLES,
    "stock.get_inventory_days": MANAGEMENT_ROLES,
    "stock.get_stock_turnover": MANAGEMENT_ROLES,
    "accounting.get_profit_and_loss": MANAGEMENT_ROLES,
    "accounting.get_trial_balance": MANAGEMENT_ROLES,
    "accounting.get_general_ledger": MANAGEMENT_ROLES,
    "core.raw_sql": {"System Manager"},
}


class PermissionGuard:
    """Checks ERPNext permissions before any tool execution.
    Uses Frappe's standard permission system -- no custom roles needed.
    Management analytics tools require manager-level roles.
    """

    def __init__(self, user: str):
        self.user = user

    def check(self, tool_name: str, tool_input: dict):
        """Verify user has ERPNext permission for this tool + input.
        Raises frappe.PermissionError if denied.
        """
        # Role-based restriction for management tools
        required_roles = ROLE_RESTRICTED_TOOLS.get(tool_name)
        if required_roles:
            user_roles = set(frappe.get_roles(self.user))
            if not user_roles.intersection(required_roles):
                frappe.throw(
                    _("This analytics tool requires a management role ({0})").format(
                        ", ".join(sorted(required_roles))
                    ),
                    frappe.PermissionError,
                )

        perm_info = TOOL_PERMISSION_MAP.get(tool_name)
        if not perm_info:
            # Unknown tool -- deny by default (fail closed)
            frappe.throw(
                _("Unknown tool: {0}. Access denied.").format(tool_name),
                frappe.PermissionError,
            )

        ptype, fixed_doctype = perm_info

        if ptype is None:
            return  # Meta tools don't require doctype permission

        doctype = fixed_doctype or tool_input.get("doctype")
        if not doctype:
            return

        # DocType-level permission
        if not frappe.has_permission(doctype, ptype=ptype, user=self.user):
            frappe.throw(
                _("You do not have {0} permission for {1}").format(ptype, doctype),
                frappe.PermissionError,
            )

        # Document-level permission (for specific records)
        doc_name = tool_input.get("name")
        if doc_name and ptype in ("read", "write", "submit", "cancel"):
            if not frappe.has_permission(
                doctype, doc=doc_name, ptype=ptype, user=self.user
            ):
                frappe.throw(
                    _("You do not have {0} permission for {1} '{2}'").format(
                        ptype, doctype, doc_name
                    ),
                    frappe.PermissionError,
                )
