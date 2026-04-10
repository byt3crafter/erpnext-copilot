import frappe
from importlib import import_module
from typing import Dict, List

# Canonical tool map: namespace.tool_name -> module.ClassName
TOOL_MAP = {
    # Core tools
    "core.get_document": "erpnext_ai_bots.tools.core.get_document.GetDocumentTool",
    "core.get_list": "erpnext_ai_bots.tools.core.get_list.GetListTool",
    "core.create_document": "erpnext_ai_bots.tools.core.create_document.CreateDocumentTool",
    "core.update_document": "erpnext_ai_bots.tools.core.update_document.UpdateDocumentTool",
    "core.submit_document": "erpnext_ai_bots.tools.core.submit_document.SubmitDocumentTool",
    "core.run_report": "erpnext_ai_bots.tools.core.run_report.RunReportTool",
    "core.raw_sql": "erpnext_ai_bots.tools.core.raw_sql.RawSQLTool",
    "core.frappe_api": "erpnext_ai_bots.tools.core.frappe_api.FrappeAPITool",
    "core.send_email": "erpnext_ai_bots.tools.core.send_email.SendEmailTool",
    "core.send_report_email": "erpnext_ai_bots.tools.core.send_report_email.SendReportEmailTool",
    "core.analyze_image": "erpnext_ai_bots.tools.core.analyze_image.AnalyzeImageTool",
    "core.read_file": "erpnext_ai_bots.tools.core.read_file.ReadFileTool",

    # Accounting tools
    "accounting.get_trial_balance": "erpnext_ai_bots.tools.accounting.trial_balance.GetTrialBalanceTool",
    "accounting.get_outstanding_invoices": "erpnext_ai_bots.tools.accounting.outstanding_invoices.GetOutstandingInvoicesTool",
    "accounting.get_bank_balances": "erpnext_ai_bots.tools.accounting.bank_balances.GetBankBalancesTool",
    "accounting.get_profit_and_loss": "erpnext_ai_bots.tools.accounting.profit_and_loss.GetProfitAndLossTool",
    "accounting.create_journal_entry": "erpnext_ai_bots.tools.accounting.journal_entry.CreateJournalEntryTool",
    "accounting.get_account_balance": "erpnext_ai_bots.tools.accounting.account_balance.GetAccountBalanceTool",
    "accounting.get_gross_margin": "erpnext_ai_bots.tools.accounting.gross_margin.GetGrossMarginTool",

    # HR tools
    "hr.get_leave_balance": "erpnext_ai_bots.tools.hr.leave_balance.GetLeaveBalanceTool",
    "hr.create_leave_application": "erpnext_ai_bots.tools.hr.leave_application.CreateLeaveApplicationTool",
    "hr.get_salary_slip": "erpnext_ai_bots.tools.hr.salary_slip.GetSalarySlipTool",
    "hr.get_attendance_summary": "erpnext_ai_bots.tools.hr.attendance.GetAttendanceSummaryTool",
    "hr.get_employee_info": "erpnext_ai_bots.tools.hr.employee_info.GetEmployeeInfoTool",

    # Stock tools
    "stock.get_stock_balance": "erpnext_ai_bots.tools.stock.stock_balance.GetStockBalanceTool",
    "stock.create_stock_entry": "erpnext_ai_bots.tools.stock.stock_entry.CreateStockEntryTool",
    "stock.get_warehouse_summary": "erpnext_ai_bots.tools.stock.warehouse_summary.GetWarehouseSummaryTool",
    "stock.get_item_info": "erpnext_ai_bots.tools.stock.item_info.GetItemInfoTool",
    "stock.get_reorder_levels": "erpnext_ai_bots.tools.stock.reorder.GetReorderLevelsTool",
    "stock.create_item": "erpnext_ai_bots.tools.stock.create_item.CreateItemTool",
    "stock.get_inventory_days": "erpnext_ai_bots.tools.stock.inventory_days.GetInventoryDaysTool",
    "stock.get_stock_turnover": "erpnext_ai_bots.tools.stock.stock_turnover.GetStockTurnoverTool",

    # Sales tools
    "sales.get_pipeline": "erpnext_ai_bots.tools.sales.pipeline.GetPipelineTool",
    "sales.create_quotation": "erpnext_ai_bots.tools.sales.quotation.CreateQuotationTool",
    "sales.get_sales_orders": "erpnext_ai_bots.tools.sales.sales_order.GetSalesOrdersTool",
    "sales.get_customer_info": "erpnext_ai_bots.tools.sales.customer_info.GetCustomerInfoTool",
    "sales.get_revenue_summary": "erpnext_ai_bots.tools.sales.revenue_summary.GetRevenueSummaryTool",
    "sales.create_customer": "erpnext_ai_bots.tools.sales.create_customer.CreateCustomerTool",
    "sales.get_branch_performance": "erpnext_ai_bots.tools.sales.branch_performance.GetBranchPerformanceTool",
    "sales.get_sales_dashboard": "erpnext_ai_bots.tools.sales.sales_dashboard.GetSalesDashboardTool",

    # Meta tools
    "meta.spawn_subagent": "erpnext_ai_bots.tools.meta.spawn_subagent.SpawnSubagentTool",
    "meta.schedule_task": "erpnext_ai_bots.tools.meta.schedule_task.ScheduleTaskTool",
    "meta.saved_report": "erpnext_ai_bots.tools.meta.saved_report.SavedReportTool",

    # Accounting (extended)
    "accounting.create_payment_entry": "erpnext_ai_bots.tools.accounting.payment_entry.CreatePaymentEntryTool",
    "accounting.get_general_ledger": "erpnext_ai_bots.tools.accounting.general_ledger.GetGeneralLedgerTool",

    # Purchase tools
    "purchase.create_purchase_order": "erpnext_ai_bots.tools.purchase.purchase_order.CreatePurchaseOrderTool",
    "purchase.get_supplier_info": "erpnext_ai_bots.tools.purchase.supplier_info.GetSupplierInfoTool",
    "purchase.get_purchase_invoices": "erpnext_ai_bots.tools.purchase.purchase_invoice.GetPurchaseInvoicesTool",
    "purchase.create_supplier": "erpnext_ai_bots.tools.purchase.create_supplier.CreateSupplierTool",

    # CRM tools
    "crm.manage_lead": "erpnext_ai_bots.tools.crm.lead.LeadTool",
    "crm.manage_opportunity": "erpnext_ai_bots.tools.crm.opportunity.OpportunityTool",

    # Project tools
    "project.manage_project": "erpnext_ai_bots.tools.project.project.ProjectTool",
    "project.manage_task": "erpnext_ai_bots.tools.project.task.TaskTool",

    # Support tools
    "support.manage_issue": "erpnext_ai_bots.tools.support.issue.IssueTool",

    # Asset tools
    "asset.manage_asset": "erpnext_ai_bots.tools.asset.asset.AssetTool",
}


class ToolRegistry:
    """Manages tool loading, namespacing, and schema generation.
    Tools are loaded lazily and cached per-request.
    """

    def __init__(self, user: str, company: str):
        self.user = user
        self.company = company
        self._cache: Dict[str, object] = {}

    def get_tool(self, namespaced_name: str):
        """Get a tool instance by its namespaced name."""
        if namespaced_name not in self._cache:
            class_path = TOOL_MAP.get(namespaced_name)
            if not class_path:
                raise ValueError(f"Unknown tool: {namespaced_name}")

            module_path, class_name = class_path.rsplit(".", 1)
            module = import_module(module_path)
            tool_class = getattr(module, class_name)
            self._cache[namespaced_name] = tool_class(
                user=self.user, company=self.company
            )

        return self._cache[namespaced_name]

    def get_all_schemas(self) -> list:
        """Return tool schemas for ALL registered tools (Anthropic format).
        Skips tools that fail to import so one broken tool doesn't crash everything.
        """
        schemas = []
        for namespaced_name in TOOL_MAP:
            try:
                tool = self.get_tool(namespaced_name)
                schemas.append(tool.schema())
            except Exception as e:
                import frappe
                frappe.log_error(
                    title=f"Tool load failed: {namespaced_name}",
                    message=str(e),
                )
        return schemas

    def get_openai_schemas(self) -> list:
        """Return tool schemas for ALL registered tools in OpenAI Responses API format.

        Anthropic format:
            {"name": "...", "description": "...", "input_schema": {"type": "object", ...}}

        OpenAI Responses API format (NOT Chat Completions):
            {"type": "function", "name": "...", "description": "...",
             "parameters": {"type": "object", ...}}

        Note: name, description, parameters are top-level siblings of type,
        NOT nested inside a "function" key. The Responses API uses a flat structure.
        Also: dots in names are replaced with underscores (API restriction).
        Skips tools that fail to import.
        """
        schemas = []
        for namespaced_name in TOOL_MAP:
            try:
                tool = self.get_tool(namespaced_name)
                anthropic_schema = tool.schema()
            except Exception as e:
                import frappe
                frappe.log_error(
                    title=f"Tool load failed: {namespaced_name}",
                    message=str(e),
                )
                continue
            # Responses API doesn't allow dots in function names
            safe_name = anthropic_schema["name"].replace(".", "_")
            openai_schema = {
                "type": "function",
                "name": safe_name,
                "description": anthropic_schema["description"],
                "parameters": anthropic_schema["input_schema"],
            }
            schemas.append(openai_schema)
        return schemas

    def get_tool_by_openai_name(self, openai_name: str):
        """Look up a tool by its OpenAI-safe name (underscores instead of dots)."""
        # Convert back: core_get_list -> core.get_list
        dotted_name = openai_name.replace("_", ".", 1)
        if dotted_name in TOOL_MAP:
            return self.get_tool(dotted_name)
        # Fallback: try direct match
        if openai_name in TOOL_MAP:
            return self.get_tool(openai_name)
        raise ValueError(f"Unknown tool: {openai_name}")

    def resolve_tool_subset(self, patterns: list) -> list:
        """Resolve glob-like patterns to tool instances.
        E.g. ["accounting.*", "core.get_document"] -> list of tool instances
        """
        tools = []
        for pattern in patterns:
            if pattern.endswith(".*"):
                namespace = pattern[:-2]
                for name in TOOL_MAP:
                    if name.startswith(namespace + "."):
                        tools.append(self.get_tool(name))
            elif pattern in TOOL_MAP:
                tools.append(self.get_tool(pattern))
        return tools
