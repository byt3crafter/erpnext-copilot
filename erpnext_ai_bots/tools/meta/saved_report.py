import frappe
from erpnext_ai_bots.tools.base import BaseTool


class SavedReportTool(BaseTool):
    name = "meta.saved_report"
    description = (
        "Create, list, run, or delete saved reports. Saved reports are reusable "
        "AI prompts that users run frequently. "
        "Actions: 'save' (create new), 'list' (show all), 'run' (execute by name), 'delete' (remove)."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "save, list, run, or delete",
        },
        "report_name": {
            "type": "string",
            "description": "Name for the report (for save/run/delete)",
        },
        "prompt": {
            "type": "string",
            "description": "The AI prompt to save (for save action)",
        },
        "category": {
            "type": "string",
            "description": "Category: General/Finance/Sales/Stock/HR",
        },
        "description": {
            "type": "string",
            "description": "What this report does (for save)",
        },
    }
    required_params = ["action"]
    action_type = "Read"

    def execute(self, action, report_name=None, prompt=None, category=None,
                description=None, **kwargs):
        action = action.lower().strip()

        if action == "save":
            return self._save(report_name, prompt, category, description)
        elif action == "list":
            return self._list()
        elif action == "run":
            return self._run(report_name)
        elif action == "delete":
            return self._delete(report_name)
        else:
            frappe.throw(
                f"Unknown action '{action}'. Valid actions are: save, list, run, delete."
            )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _save(self, report_name, prompt, category, description):
        if not report_name:
            frappe.throw("report_name is required to save a report.")
        if not prompt:
            frappe.throw("prompt is required to save a report.")

        doc = frappe.get_doc({
            "doctype": "AI Saved Report",
            "report_name": report_name,
            "prompt": prompt,
            "user": frappe.session.user,
            "category": category or "General",
            "description": description or "",
        })
        doc.insert(ignore_permissions=False)

        return {
            "status": "saved",
            "name": doc.name,
            "report_name": doc.report_name,
            "message": f"Report '{report_name}' saved as {doc.name}. Run it any time by saying 'run report {report_name}'.",
        }

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def _list(self):
        reports = frappe.get_all(
            "AI Saved Report",
            filters={"user": frappe.session.user},
            fields=["name", "report_name", "category", "description", "last_run", "run_count"],
            order_by="report_name asc",
        )
        return {
            "reports": reports,
            "count": len(reports),
        }

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run(self, report_name):
        if not report_name:
            frappe.throw("report_name is required to run a report.")

        # Try exact document name first, then by report_name field
        doc = self._find_report(report_name)
        if not doc:
            return {
                "status": "not_found",
                "message": f"No saved report found matching '{report_name}'.",
            }

        # Update last_run and run_count
        frappe.db.set_value(
            "AI Saved Report",
            doc.name,
            {
                "last_run": frappe.utils.now_datetime(),
                "run_count": (doc.run_count or 0) + 1,
            },
        )

        return {
            "status": "ready",
            "report_name": doc.report_name,
            "prompt": doc.prompt,
            "message": (
                f"Running saved report '{doc.report_name}'. "
                f"Executing prompt: {doc.prompt}"
            ),
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def _delete(self, report_name):
        if not report_name:
            frappe.throw("report_name is required to delete a report.")

        doc = self._find_report(report_name)
        if not doc:
            return {
                "status": "not_found",
                "message": f"No saved report found matching '{report_name}'.",
            }

        # Only the owner or System Manager may delete
        if doc.user != frappe.session.user and "System Manager" not in frappe.get_roles():
            frappe.throw(
                f"You do not have permission to delete report '{doc.report_name}'.",
                frappe.PermissionError,
            )

        doc_name = doc.name
        display_name = doc.report_name
        frappe.delete_doc("AI Saved Report", doc_name, ignore_permissions=False)

        return {
            "status": "deleted",
            "name": doc_name,
            "message": f"Report '{display_name}' has been deleted.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_report(self, report_name):
        """Find by exact doc name, then by report_name field (owner-scoped)."""
        if frappe.db.exists("AI Saved Report", report_name):
            doc = frappe.get_doc("AI Saved Report", report_name)
            if doc.user == frappe.session.user or "System Manager" in frappe.get_roles():
                return doc

        matches = frappe.get_all(
            "AI Saved Report",
            filters={
                "report_name": ["like", f"%{report_name}%"],
                "user": frappe.session.user,
            },
            fields=["name", "report_name", "prompt", "user", "run_count"],
            limit_page_length=5,
            order_by="report_name asc",
        )
        if not matches:
            return None
        return frappe.get_doc("AI Saved Report", matches[0]["name"])
