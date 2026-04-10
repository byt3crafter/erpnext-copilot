import frappe
from erpnext_ai_bots.tools.base import BaseTool


class RunReportTool(BaseTool):
    name = "core.run_report"
    description = "Execute an ERPNext report and return the results."
    parameters = {
        "report_name": {
            "type": "string",
            "description": "Name of the report, e.g. 'General Ledger', 'Stock Balance'",
        },
        "filters": {"type": "object", "description": "Report filters"},
    }
    required_params = ["report_name"]
    action_type = "Report"
    required_ptype = "read"

    def execute(self, report_name, filters=None, **kwargs):
        result = frappe.call(
            "frappe.desk.query_report.run",
            report_name=report_name,
            filters=filters or {},
        )
        data = result.get("result", [])[:50]
        columns = result.get("columns", [])
        return {
            "columns": [
                c.get("label", c.get("fieldname", "")) if isinstance(c, dict) else str(c)
                for c in columns
            ],
            "data": data,
            "total_rows": len(result.get("result", [])),
            "showing": len(data),
        }
