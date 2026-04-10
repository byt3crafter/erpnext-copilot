import frappe
import json


class StreamBridge:
    """Bridges the Anthropic streaming API to Frappe's Socket.IO realtime system.

    Events pushed to client:
      - ai_chunk:       {session_id, text}         -- text delta
      - ai_tool_start:  {session_id, tool, input}   -- tool execution starting
      - ai_tool_result: {session_id, tool, result}   -- tool execution complete
      - ai_done:        {session_id}                 -- response complete
      - ai_error:       {session_id, error}          -- error occurred
    """

    def __init__(self, session_id: str, user: str):
        self.session_id = session_id
        self.user = user
        self._tool_starts_sent = set()  # track tool IDs already announced

    def process_stream(self, stream):
        """Consume the Anthropic stream, forwarding text chunks to the client.
        Returns the final accumulated Message object.

        Emits ai_tool_start with a friendly name during the stream so the
        frontend can show thinking steps immediately. The tool name is
        recorded in _tool_starts_sent so send_tool_start() will not
        duplicate it after the stream finishes.
        """
        for event in stream:
            if not hasattr(event, "type"):
                continue
            if event.type == "content_block_delta":
                if hasattr(event.delta, "text"):
                    self._publish("ai_chunk", {
                        "session_id": self.session_id,
                        "text": event.delta.text,
                    })
            elif event.type == "content_block_start":
                if hasattr(event.content_block, "type"):
                    if event.content_block.type == "tool_use":
                        tool_name = event.content_block.name
                        friendly = self._friendly_tool_name(tool_name, {})
                        self._tool_starts_sent.add(tool_name)
                        self._publish("ai_tool_start", {
                            "session_id": self.session_id,
                            "tool": friendly,
                        })

        return stream.get_final_message()

    def send_tool_start(self, tool_name: str, tool_input: dict):
        # Skip if already announced during Anthropic stream processing.
        # For the OpenAI path, _tool_starts_sent is always empty so this
        # always fires.
        if tool_name in self._tool_starts_sent:
            self._tool_starts_sent.discard(tool_name)
            return
        self._publish("ai_tool_start", {
            "session_id": self.session_id,
            "tool": self._friendly_tool_name(tool_name, tool_input),
            "input": self._safe_summary(tool_input),
        })

    def send_tool_result(self, tool_name: str, result: dict):
        self._publish("ai_tool_result", {
            "session_id": self.session_id,
            "tool": self._friendly_tool_name(tool_name, {}),
            "result": self._safe_summary(result),
        })

    def _friendly_tool_name(self, tool_name: str, tool_input: dict) -> str:
        """Convert technical tool names to user-friendly descriptions."""
        doctype = tool_input.get("doctype", "")
        name = tool_input.get("name", "")

        friendly = {
            "core.get_list": f"Searching {doctype or 'records'}",
            "core.get_document": f"Looking up {doctype} {name}".strip(),
            "core.create_document": f"Creating {doctype or 'document'}",
            "core.update_document": f"Updating {doctype} {name}".strip(),
            "core.submit_document": f"Submitting {doctype} {name}".strip(),
            "core.run_report": f"Running report",
            "accounting.get_trial_balance": "Fetching trial balance",
            "accounting.get_outstanding_invoices": "Checking outstanding invoices",
            "accounting.get_bank_balances": "Checking bank balances",
            "accounting.get_profit_and_loss": "Running profit & loss report",
            "accounting.create_journal_entry": "Creating journal entry",
            "accounting.get_account_balance": "Checking account balance",
            "hr.get_leave_balance": "Checking leave balance",
            "hr.create_leave_application": "Creating leave application",
            "hr.get_salary_slip": "Looking up salary slip",
            "hr.get_attendance_summary": "Checking attendance",
            "hr.get_employee_info": "Looking up employee info",
            "stock.get_stock_balance": "Checking stock levels",
            "stock.create_stock_entry": "Creating stock entry",
            "stock.get_warehouse_summary": "Checking warehouse summary",
            "stock.get_item_info": "Looking up item details",
            "stock.get_reorder_levels": "Checking reorder levels",
            "sales.get_pipeline": "Checking sales pipeline",
            "sales.create_quotation": "Creating quotation",
            "sales.get_sales_orders": "Looking up sales orders",
            "sales.get_customer_info": "Looking up customer info",
            "sales.get_revenue_summary": "Checking revenue summary",
            "core.raw_sql": "Running database query",
            "core.frappe_api": "Querying ERPNext data",
            "core.send_email": "Sending email",
            "core.analyze_image": "Analyzing image",
            "core.read_file": "Reading file",
            "meta.spawn_subagent": "Working on complex task",
            "meta.schedule_task": "Setting up scheduled task",
            "meta.saved_report": "Managing saved reports",
            "accounting.create_payment_entry": "Creating payment entry",
            "accounting.get_general_ledger": "Fetching general ledger",
            "purchase.create_purchase_order": "Creating purchase order",
            "purchase.get_supplier_info": "Looking up supplier info",
            "purchase.get_purchase_invoices": "Fetching purchase invoices",
            "purchase.create_supplier": "Creating supplier",
            "sales.create_customer": "Creating customer",
            "stock.create_item": "Creating item",
            "crm.manage_lead": "Managing lead",
            "crm.manage_opportunity": "Managing opportunity",
            "project.manage_project": "Managing project",
            "project.manage_task": "Managing task",
            "support.manage_issue": "Managing support issue",
            "asset.manage_asset": "Looking up asset info",
        }
        return friendly.get(tool_name, f"Looking up {tool_name.split('.')[-1].replace('_', ' ')}")

    def send_done(self):
        self._publish("ai_done", {"session_id": self.session_id})

    def send_error(self, error_message: str):
        self._publish("ai_error", {
            "session_id": self.session_id,
            "error": error_message,
        })

    def _publish(self, event: str, data: dict):
        frappe.publish_realtime(
            event=event,
            message=data,
            user=self.user,
            after_commit=False,
        )

    def _safe_summary(self, data: dict, max_len: int = 500) -> dict:
        """Truncate large payloads before sending to frontend."""
        summary = {}
        for key, value in data.items():
            s = str(value)
            if len(s) > max_len:
                summary[key] = s[:max_len] + "..."
            else:
                summary[key] = value
        return summary
