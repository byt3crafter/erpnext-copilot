"""task_runner.py — Frappe scheduled job that finds and executes due AI tasks.

Runs every 15 minutes via cron (see hooks.py).
Each task failure is isolated: one bad task never stops the others.
Heavy execution is offloaded to frappe.enqueue so the scheduler thread
returns quickly.
"""
import frappe
import json


def run_scheduled_tasks():
    """Entry point called by the Frappe scheduler.

    Finds all Active AI Scheduled Tasks whose next_run is in the past and
    enqueues each one individually for background execution.
    """
    now = frappe.utils.now_datetime()

    due_tasks = frappe.get_all(
        "AI Scheduled Task",
        filters={
            "status": "Active",
            "next_run": ["<=", now],
        },
        fields=[
            "name", "user", "company", "prompt", "context_notes",
            "trigger_type", "title",
        ],
    )

    if not due_tasks:
        return

    for task_data in due_tasks:
        try:
            frappe.enqueue(
                "erpnext_ai_bots.utils.task_runner._execute_task_background",
                queue="long",
                timeout=600,
                task_name=task_data["name"],
                now=False,  # always background — never inline in scheduler
            )
        except Exception:
            frappe.log_error(
                title=f"Failed to enqueue Scheduled Task: {task_data['name']}",
                message=frappe.get_traceback(),
            )


def _execute_task_background(task_name: str):
    """Called by the background worker for a single task.

    This wrapper reloads the task from DB (the enqueued job may run after a
    short delay) and delegates to _execute_task, ensuring that any crash is
    isolated and logged without taking down the worker.
    """
    try:
        task_data = frappe.get_all(
            "AI Scheduled Task",
            filters={"name": task_name, "status": "Active"},
            fields=[
                "name", "user", "company", "prompt", "context_notes",
                "trigger_type", "title",
            ],
        )
        if not task_data:
            # Task was cancelled or already ran between enqueue and execution
            return

        now = frappe.utils.now_datetime()
        _execute_task(task_data[0], now)

    except Exception:
        frappe.log_error(
            title=f"Scheduled Task Failed: {task_name}",
            message=frappe.get_traceback(),
        )
        frappe.db.set_value("AI Scheduled Task", task_name, "status", "Failed")
        frappe.db.commit()


def _execute_task(task_data: dict, now):
    """Run a single due AI Scheduled Task end-to-end.

    Steps:
      1. Set the Frappe user context to the task owner.
      2. Create a new AI Chat Session titled "[Scheduled] {title}".
      3. Build the full prompt (task prompt + context_notes).
      4. Run the Orchestrator synchronously inside this background worker.
      5. Extract the AI's final text response from the session messages.
      6. Persist last_run, last_result, run_count.
      7. Advance next_run (or mark Completed for Once tasks).
      8. Notify the user via realtime push.
    """
    from erpnext_ai_bots.agent.orchestrator import Orchestrator

    task_name = task_data["name"]
    user = task_data["user"]
    company = task_data.get("company") or frappe.defaults.get_user_default("company", user)

    # Switch Frappe's thread-local user so permission checks run as the owner
    frappe.set_user(user)

    # 1. Create a dedicated chat session for this scheduled run
    session = frappe.get_doc({
        "doctype": "AI Chat Session",
        "user": user,
        "company": company,
        "status": "Active",
        "title": f"[Scheduled] {task_data['title']}",
        "category": "General",
    })
    session.insert(ignore_permissions=True)
    frappe.db.commit()

    session_id = session.name

    # 2. Build the full prompt including any context notes
    full_prompt = task_data["prompt"].strip()
    if task_data.get("context_notes"):
        full_prompt = (
            f"{full_prompt}\n\n"
            f"Additional context: {task_data['context_notes'].strip()}"
        )

    # 3. Run the orchestrator (this is a blocking call inside the worker)
    try:
        agent = Orchestrator(user=user, session_id=session_id, company=company)
        agent.handle_message(full_prompt)
    except Exception:
        frappe.log_error(
            title=f"Orchestrator error in Scheduled Task {task_name}",
            message=frappe.get_traceback(),
        )
        # We continue so we can at least update the run metadata and notify

    # 4. Extract the AI's final response text from the session
    ai_response = _extract_last_assistant_text(session_id)

    # 5. Persist execution metadata on the task
    run_count = frappe.db.get_value("AI Scheduled Task", task_name, "run_count") or 0

    update_values = {
        "last_run": now,
        "last_result": (ai_response or "")[:5000],  # cap at 5000 chars
        "run_count": run_count + 1,
    }

    if task_data["trigger_type"] == "Once":
        update_values["status"] = "Completed"
        update_values["next_run"] = None
    else:
        # Advance next_run by reloading the doc and recalculating
        task_doc = frappe.get_doc("AI Scheduled Task", task_name)
        next_run = task_doc.calculate_next_run()
        update_values["next_run"] = next_run

    frappe.db.set_value("AI Scheduled Task", task_name, update_values)
    frappe.db.commit()

    # 6. Notify the user via Socket.IO realtime
    _notify_user(user, task_data["title"], task_name, ai_response, session_id)


def _extract_last_assistant_text(session_id: str) -> str:
    """Pull the final assistant text message from the session's messages_json."""
    messages_json = frappe.db.get_value("AI Chat Session", session_id, "messages_json")
    if not messages_json:
        return ""

    try:
        messages = json.loads(messages_json)
    except (json.JSONDecodeError, ValueError):
        return ""

    # Walk messages in reverse to find the last assistant text block
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            combined = "\n".join(filter(None, text_parts))
            if combined:
                return combined

    return ""


def _notify_user(user: str, task_title: str, task_name: str, result: str, session_id: str):
    """Push a realtime notification to the task owner's browser.

    Also creates a persistent Frappe Notification Log entry (visible in the
    ERPNext notification bell) and sends a best-effort email to the user.
    """
    result_text = result or "Task completed."
    preview = result_text[:300]
    if len(result_text) > 300:
        preview += "..."

    # 1. Socket.IO realtime push (existing behaviour — kept unchanged)
    frappe.publish_realtime(
        event="ai_scheduled_task_done",
        message={
            "task_name": task_name,
            "title": task_title,
            "session_id": session_id,
            "preview": preview,
        },
        user=user,
        after_commit=False,
    )

    # 2. Persistent Notification Log — shows in Frappe's top-right bell icon
    try:
        frappe.get_doc({
            "doctype": "Notification Log",
            "for_user": user,
            "type": "Alert",
            "document_type": "AI Scheduled Task",
            "document_name": task_name,
            "subject": f"AI Task Complete: {task_title}",
            "email_content": result_text[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        # Notification Log failure must not break the task runner
        frappe.log_error(
            title=f"Failed to create Notification Log for task {task_name}",
            message=frappe.get_traceback(),
        )

    # 3. Email notification — best-effort, never raises
    try:
        frappe.sendmail(
            recipients=[user],
            subject=f"[AI Oracle] {task_title}",
            message=(
                f"<p>Your scheduled AI task has completed:</p>"
                f"<p><b>{frappe.utils.escape_html(task_title)}</b></p>"
                f"<p>{frappe.utils.escape_html(preview)}</p>"
            ),
            now=True,
        )
    except Exception:
        pass  # Email is best-effort
