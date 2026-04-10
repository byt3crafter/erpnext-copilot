import frappe
from erpnext_ai_bots.tools.base import BaseTool


class ScheduleTaskTool(BaseTool):
    name = "meta.schedule_task"
    description = (
        "Schedule a task for the AI to execute later. Use this when the user asks "
        "to be reminded about something, wants a recurring report, or needs follow-up "
        "on a document. "
        "Actions: 'create' (new task), 'list' (show user's tasks), 'cancel' (stop a task), "
        "'pause' (pause a recurring task), 'resume' (resume a paused task)."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "One of: create, list, cancel, pause, resume",
        },
        "title": {
            "type": "string",
            "description": "Short description of the task (for create)",
        },
        "prompt": {
            "type": "string",
            "description": "The instruction the AI will execute when the task triggers (for create)",
        },
        "trigger_type": {
            "type": "string",
            "description": "Once, Daily, Weekly, or Monthly (for create)",
        },
        "trigger_date": {
            "type": "string",
            "description": "YYYY-MM-DD date for 'Once' tasks (for create)",
        },
        "trigger_time": {
            "type": "string",
            "description": "HH:MM time of day to run, default 08:00 (for create)",
        },
        "day_of_week": {
            "type": "string",
            "description": "Day name for Weekly tasks, e.g. Monday (for create)",
        },
        "day_of_month": {
            "type": "integer",
            "description": "Day of month (1-28) for Monthly tasks (for create)",
        },
        "task_name": {
            "type": "string",
            "description": "The task ID (AI-TASK-xxxxx) for cancel/pause/resume actions",
        },
        "context_notes": {
            "type": "string",
            "description": "Additional context for the AI when executing the task (for create)",
        },
    }
    required_params = ["action"]
    action_type = "Create"
    required_ptype = None  # Meta tool — no DocType permission required

    def execute(self, **kwargs) -> dict:
        action = kwargs.get("action", "").lower().strip()

        if action == "create":
            return self._create(kwargs)
        elif action == "list":
            return self._list()
        elif action == "cancel":
            return self._set_status(kwargs.get("task_name"), "Completed", "cancelled")
        elif action == "pause":
            return self._set_status(kwargs.get("task_name"), "Paused", "paused")
        elif action == "resume":
            return self._resume(kwargs.get("task_name"))
        else:
            return {"error": f"Unknown action '{action}'. Must be one of: create, list, cancel, pause, resume."}

    # ── actions ──────────────────────────────────────────────────────

    def _create(self, kwargs: dict) -> dict:
        required = ["title", "prompt", "trigger_type"]
        missing = [f for f in required if not kwargs.get(f)]
        if missing:
            return {"error": f"Missing required fields for create: {', '.join(missing)}"}

        trigger_type = kwargs["trigger_type"].strip().capitalize()
        if trigger_type not in ("Once", "Daily", "Weekly", "Monthly"):
            return {"error": f"trigger_type must be Once, Daily, Weekly, or Monthly. Got: {trigger_type}"}

        # Normalise time to HH:MM:SS
        raw_time = kwargs.get("trigger_time", "08:00")
        trigger_time = self._normalise_time(raw_time)

        doc = frappe.get_doc({
            "doctype": "AI Scheduled Task",
            "user": self.user,
            "company": self.company or frappe.defaults.get_user_default("company", self.user),
            "status": "Active",
            "title": kwargs["title"],
            "trigger_type": trigger_type,
            "trigger_date": kwargs.get("trigger_date"),
            "trigger_time": trigger_time,
            "day_of_week": kwargs.get("day_of_week"),
            "day_of_month": kwargs.get("day_of_month"),
            "prompt": kwargs["prompt"],
            "context_notes": kwargs.get("context_notes", ""),
            "run_count": 0,
        })

        # Calculate next_run before insert (before_insert hook also does this,
        # but we want it in the response immediately)
        next_run = doc.calculate_next_run()
        if next_run:
            doc.next_run = next_run

        doc.insert(ignore_permissions=False)
        frappe.db.commit()

        return {
            "success": True,
            "task_name": doc.name,
            "title": doc.title,
            "trigger_type": doc.trigger_type,
            "next_run": str(doc.next_run) if doc.next_run else None,
            "message": (
                f"Scheduled task '{doc.title}' created successfully as {doc.name}. "
                f"It will run {trigger_type.lower()}"
                + (f" on {kwargs.get('trigger_date')}" if trigger_type == "Once" else "")
                + (f" on {kwargs.get('day_of_week')}s" if trigger_type == "Weekly" else "")
                + (f" on the {kwargs.get('day_of_month')}th of each month" if trigger_type == "Monthly" else "")
                + f" at {raw_time}."
            ),
        }

    def _list(self) -> dict:
        tasks = frappe.get_all(
            "AI Scheduled Task",
            filters={"user": self.user, "status": ["in", ["Active", "Paused"]]},
            fields=["name", "title", "status", "trigger_type", "next_run", "last_run", "run_count"],
            order_by="next_run asc",
        )
        if not tasks:
            return {"tasks": [], "message": "You have no active or paused scheduled tasks."}

        return {
            "tasks": [
                {
                    "id": t["name"],
                    "title": t["title"],
                    "status": t["status"],
                    "trigger_type": t["trigger_type"],
                    "next_run": str(t["next_run"]) if t.get("next_run") else "Not set",
                    "last_run": str(t["last_run"]) if t.get("last_run") else "Never",
                    "run_count": t["run_count"],
                }
                for t in tasks
            ],
            "count": len(tasks),
        }

    def _set_status(self, task_name: str, new_status: str, verb: str) -> dict:
        if not task_name:
            return {"error": "task_name is required (e.g. AI-TASK-00001)."}

        task = self._get_task_for_user(task_name)
        if not task:
            return {"error": f"Task '{task_name}' not found or does not belong to you."}

        frappe.db.set_value("AI Scheduled Task", task_name, "status", new_status)
        frappe.db.commit()

        return {
            "success": True,
            "task_name": task_name,
            "message": f"Task '{task['title']}' ({task_name}) has been {verb}.",
        }

    def _resume(self, task_name: str) -> dict:
        if not task_name:
            return {"error": "task_name is required (e.g. AI-TASK-00001)."}

        task = self._get_task_for_user(task_name)
        if not task:
            return {"error": f"Task '{task_name}' not found or does not belong to you."}

        # Reload full doc to recalculate next_run
        doc = frappe.get_doc("AI Scheduled Task", task_name)
        next_run = doc.calculate_next_run()

        frappe.db.set_value(
            "AI Scheduled Task",
            task_name,
            {"status": "Active", "next_run": next_run},
        )
        frappe.db.commit()

        return {
            "success": True,
            "task_name": task_name,
            "next_run": str(next_run) if next_run else None,
            "message": (
                f"Task '{doc.title}' ({task_name}) has been resumed. "
                f"Next run: {next_run or 'unscheduled'}."
            ),
        }

    # ── helpers ──────────────────────────────────────────────────────

    def _get_task_for_user(self, task_name: str) -> dict | None:
        """Return lightweight task dict only if it belongs to self.user."""
        rows = frappe.get_all(
            "AI Scheduled Task",
            filters={"name": task_name, "user": self.user},
            fields=["name", "title", "status"],
        )
        return rows[0] if rows else None

    @staticmethod
    def _normalise_time(raw: str) -> str:
        """Ensure time is in HH:MM:SS format."""
        parts = str(raw).strip().split(":")
        hour = parts[0].zfill(2) if len(parts) > 0 else "08"
        minute = parts[1].zfill(2) if len(parts) > 1 else "00"
        second = parts[2].zfill(2) if len(parts) > 2 else "00"
        return f"{hour}:{minute}:{second}"
