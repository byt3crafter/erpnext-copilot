import csv
import io
import frappe
import json
from frappe import _
from erpnext_ai_bots.guards.rate_limiter import RateLimiter


@frappe.whitelist()
def upload_file(session_id: str = None):
    """Upload a file and return its URL. Optionally attach to a session."""
    if not frappe.request.files:
        frappe.throw(_("No file uploaded"))

    file = frappe.request.files.get("file")
    if not file:
        frappe.throw(_("No file found in request"))

    # Verify session ownership when a session_id is provided
    if session_id:
        session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
        if session_user and session_user != frappe.session.user:
            frappe.throw(_("Access denied"), frappe.PermissionError)

    file_content = file.read()
    ret = frappe.get_doc({
        "doctype": "File",
        "file_name": file.filename,
        "content": file_content,
        "attached_to_doctype": "AI Chat Session" if session_id else None,
        "attached_to_name": session_id if session_id else None,
        "is_private": 1,
    })
    ret.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "file_url": ret.file_url,
        "file_name": ret.file_name,
        "file_type": file.content_type,
        "file_size": ret.file_size,
    }


# ── Category keyword maps ────────────────────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "Finance": [
        "invoice", "payment", "journal", "bank", "balance",
        "p&l", "profit", "loss", "ledger", "account", "tax",
        "receivable", "payable", "expense", "budget", "supplier",
        "purchase", "overdue", "outstanding", "credit", "debit",
        "revenue", "cost", "financial", "fiscal",
    ],
    "Sales": [
        "quotation", "customer", "order", "pipeline", "quote",
        "lead", "opportunity", "crm", "sale", "deal", "prospect",
        "contract", "discount", "pricing", "client",
    ],
    "Stock": [
        "stock", "item", "warehouse", "inventory", "reorder",
        "material", "bin", "transfer", "receipt", "delivery",
        "batch", "serial", "product", "goods",
    ],
    "HR": [
        "leave", "salary", "employee", "attendance", "hr",
        "payroll", "appraisal", "recruitment", "department",
        "overtime", "holiday", "staff", "worker",
    ],
}


def _auto_categorize(text: str) -> str:
    """Return the best-matching category for a message string."""
    lower = text.lower()
    scores = {cat: 0 for cat in _CATEGORY_KEYWORDS}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[cat] += 1
    best_cat = max(scores, key=lambda c: scores[c])
    return best_cat if scores[best_cat] > 0 else "General"


def _has_openai_token() -> bool:
    """Check if ANY active OpenAI OAuth token exists (global shared connection)."""
    tokens = frappe.get_all(
        "AI OpenAI Token",
        filters={"status": "Connected"},
        limit_page_length=1,
        pluck="name",
    )
    return len(tokens) > 0


@frappe.whitelist()
def get_companies():
    """Get all companies the current user has read access to.

    System Managers and Administrators see every company. Other users see
    companies permitted by standard Frappe User Permissions.
    """
    user = frappe.session.user
    roles = frappe.get_roles(user)
    # System Manager / Administrator bypass User Permissions
    skip_perms = user == "Administrator" or "System Manager" in roles

    if skip_perms:
        return frappe.get_all(
            "Company",
            fields=["name", "company_name", "default_currency"],
            order_by="name asc",
            limit_page_length=0,
            ignore_permissions=True,
        )

    return frappe.get_all(
        "Company",
        fields=["name", "company_name", "default_currency"],
        order_by="name asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def send_message(message: str, session_id: str = None, company: str = None, image_url: str = None):
    """Main chat endpoint. Initiates agent processing.

    The response text is NOT returned in this HTTP response.
    It is streamed via Socket.IO events (ai_chunk, ai_done, etc.).
    """
    if not message or not message.strip():
        frappe.throw(_("Message cannot be empty"))

    user = frappe.session.user
    if not company:
        company = frappe.defaults.get_user_default("company", user)

    # Check if provider requires OpenAI token
    settings = frappe.get_cached_doc("AI Bot Settings")
    provider = settings.provider or "Anthropic"
    if provider == "OpenAI (ChatGPT OAuth)" and not _has_openai_token():
        return {
            "status": "no_token",
            "message": _("Please connect your ChatGPT account to use the AI Assistant."),
        }

    # Rate limiting
    limiter = RateLimiter(user)
    limiter.check()

    # Get or create session
    if not session_id:
        session = frappe.get_doc({
            "doctype": "AI Chat Session",
            "user": user,
            "company": company,
            "status": "Active",
            "title": message[:100],
            "category": _auto_categorize(message),
            "messages_json": "[]",
            "model_used": frappe.get_cached_doc("AI Bot Settings").model_name,
        })
        session.insert(ignore_permissions=True)
        session_id = session.name
        frappe.db.commit()
    else:
        session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
        if session_user != user:
            frappe.throw(_("You do not own this session"), frappe.PermissionError)

    limiter.increment()

    # Enqueue agent processing as background job
    frappe.enqueue(
        "erpnext_ai_bots.agent.orchestrator.run_orchestrator",
        queue="default",
        timeout=300,
        is_async=True,
        user=user,
        session_id=session_id,
        message=message,
        company=company,
        image_url=image_url,
    )

    return {"session_id": session_id, "status": "processing"}


@frappe.whitelist()
def get_sessions(limit: int = 20, offset: int = 0):
    """Get the current user's chat sessions."""
    return frappe.get_all(
        "AI Chat Session",
        filters={"user": frappe.session.user},
        fields=[
            "name", "title", "status", "category", "message_count",
            "last_message_at", "total_cost_usd", "creation", "pinned",
        ],
        order_by="COALESCE(last_message_at, creation) desc",
        limit_page_length=min(int(limit), 50),
        limit_start=int(offset),
    )


@frappe.whitelist()
def toggle_pin(session_id: str):
    """Toggle the pinned state of a chat session."""
    session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
    if session_user != frappe.session.user:
        frappe.throw(_("Access denied"), frappe.PermissionError)
    current = frappe.db.get_value("AI Chat Session", session_id, "pinned")
    new_val = 0 if current else 1
    frappe.db.set_value("AI Chat Session", session_id, "pinned", new_val)
    frappe.db.commit()
    return {"pinned": bool(new_val)}


@frappe.whitelist()
def get_history(session_id: str):
    """Get full conversation history for a session."""
    user = frappe.session.user
    session = frappe.get_doc("AI Chat Session", session_id)

    if session.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Access denied"), frappe.PermissionError)

    return {
        "session_id": session_id,
        "title": session.title,
        "status": session.status,
        "messages": json.loads(session.messages_json or "[]"),
        "total_cost_usd": session.total_cost_usd,
        "total_input_tokens": session.total_input_tokens,
        "total_output_tokens": session.total_output_tokens,
    }


@frappe.whitelist()
def close_session(session_id: str):
    """Close/archive a chat session."""
    session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
    if session_user != frappe.session.user:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    frappe.db.set_value("AI Chat Session", session_id, "status", "Closed")
    frappe.db.commit()
    return {"status": "closed"}


@frappe.whitelist()
def rename_session(session_id: str, title: str):
    """Rename a chat session's title."""
    session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
    if session_user != frappe.session.user:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    title = (title or "").strip()[:200]
    if not title:
        frappe.throw(_("Title cannot be empty"))

    frappe.db.set_value("AI Chat Session", session_id, "title", title)
    frappe.db.commit()
    return {"status": "renamed", "title": title}


@frappe.whitelist()
def delete_session(session_id: str):
    """Permanently delete a chat session and its linked audit logs."""
    session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
    if session_user != frappe.session.user:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    # Delete linked AI Audit Log records first to avoid orphaned references
    audit_logs = frappe.get_all(
        "AI Audit Log",
        filters={"session": session_id},
        pluck="name",
    )
    for log_name in audit_logs:
        frappe.delete_doc("AI Audit Log", log_name, ignore_permissions=True, force=True)

    frappe.delete_doc("AI Chat Session", session_id, ignore_permissions=True, force=True)
    frappe.db.commit()
    return {"status": "deleted"}


@frappe.whitelist()
def categorize_session(session_id: str, category: str):
    """Manually set the category for a chat session."""
    valid_categories = {"General", "Finance", "Sales", "Stock", "HR"}
    if category not in valid_categories:
        frappe.throw(_("Invalid category: {0}").format(category))

    session_user = frappe.db.get_value("AI Chat Session", session_id, "user")
    if session_user != frappe.session.user:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    frappe.db.set_value("AI Chat Session", session_id, "category", category)
    frappe.db.commit()
    return {"status": "categorized", "category": category}


@frappe.whitelist()
def confirm_action(action_type: str, doctype: str, name: str):
    """Explicit confirmation endpoint for write actions."""
    if action_type == "submit":
        frappe.has_permission(doctype, doc=name, ptype="submit", throw=True)
        doc = frappe.get_doc(doctype, name)
        doc.submit()
        return {"status": "submitted", "name": doc.name}
    elif action_type == "cancel":
        frappe.has_permission(doctype, doc=name, ptype="cancel", throw=True)
        doc = frappe.get_doc(doctype, name)
        doc.cancel()
        return {"status": "cancelled", "name": doc.name}
    elif action_type == "delete":
        frappe.has_permission(doctype, doc=name, ptype="delete", throw=True)
        frappe.delete_doc(doctype, name)
        return {"status": "deleted", "name": name}
    else:
        frappe.throw(_("Unknown action type: {0}").format(action_type))


# ── Export endpoints ──────────────────────────────────────────────────────────


def _load_session_for_export(session_id: str):
    """Verify ownership and return (session doc, messages list).

    Raises PermissionError if the current user does not own the session.
    """
    user = frappe.session.user
    session = frappe.get_doc("AI Chat Session", session_id)
    if session.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Access denied"), frappe.PermissionError)

    messages = json.loads(session.messages_json or "[]")
    return session, messages


def _extract_text_content(content) -> str:
    """Flatten a message content value to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(filter(None, parts))
    return ""


@frappe.whitelist()
def export_session_html(session_id: str):
    """Export a chat session as a self-contained HTML page suitable for printing / PDF.

    Returns the HTML string directly so the frontend can open it in a new tab
    via a Blob URL (no file-download plumbing needed server-side).
    """
    session, messages = _load_session_for_export(session_id)

    title = frappe.utils.escape_html(session.title or session_id)
    date = frappe.utils.formatdate(
        (session.last_message_at or session.creation or "").split(" ")[0]
    )
    visible = [m for m in messages if m.get("role") in ("user", "assistant")]
    count = len(visible)

    messages_html_parts = []
    for msg in visible:
        role = msg.get("role", "")
        text = frappe.utils.escape_html(_extract_text_content(msg.get("content", "")))
        css_class = "user" if role == "user" else "bot"
        label = "You" if role == "user" else "AI Assistant"
        ts_raw = msg.get("timestamp", "")
        ts = frappe.utils.escape_html(str(ts_raw))
        messages_html_parts.append(
            f'<div class="msg {css_class}">'
            f'<div class="msg-label">{label}'
            + (f' &mdash; <small>{ts}</small>' if ts else "")
            + f"</div>"
            f"<div class=\"msg-body\">{text}</div>"
            f"</div>"
        )

    messages_html = "\n".join(messages_html_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.55;
    color: #1e293b;
    background: #f8fafc;
    padding: 40px 20px;
  }}
  .page {{
    max-width: 800px;
    margin: 0 auto;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,.08);
    overflow: hidden;
  }}
  .page-header {{
    background: linear-gradient(135deg, #6c5ce7 0%, #4c3eb0 100%);
    color: #fff;
    padding: 24px 32px;
  }}
  .page-header h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
  .page-header p  {{ font-size: 13px; opacity: 0.85; }}
  .page-body {{ padding: 24px 32px; display: flex; flex-direction: column; gap: 12px; }}
  .msg {{
    padding: 10px 14px;
    border-radius: 12px;
    max-width: 80%;
    word-break: break-word;
    white-space: pre-wrap;
  }}
  .msg-label {{
    font-size: 11px;
    font-weight: 600;
    opacity: 0.7;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .user {{
    background: #6c5ce7;
    color: #fff;
    align-self: flex-end;
    margin-left: auto;
    border-bottom-right-radius: 4px;
  }}
  .bot {{
    background: #f1f5f9;
    color: #1e293b;
    border-left: 3px solid #6c5ce7;
    align-self: flex-start;
    border-bottom-left-radius: 4px;
  }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }}
  th, td {{ padding: 6px 10px; border: 1px solid #e2e8f0; text-align: left; }}
  th {{ background: #f8fafc; font-weight: 600; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .page {{ box-shadow: none; border-radius: 0; }}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="page-header">
    <h1>{title}</h1>
    <p>Session: {frappe.utils.escape_html(session_id)} &nbsp;&middot;&nbsp; Date: {date} &nbsp;&middot;&nbsp; {count} message{"s" if count != 1 else ""}</p>
  </div>
  <div class="page-body">
{messages_html}
  </div>
</div>
</body>
</html>"""

    return {"html": html, "title": session.title or session_id}


@frappe.whitelist()
def export_session_csv(session_id: str):
    """Export a chat session as a CSV file download.

    Sets frappe.response to trigger a file download in the browser.
    Columns: Timestamp, Role, Content.
    """
    session, messages = _load_session_for_export(session_id)

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Timestamp", "Role", "Content"])

    for msg in messages:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        ts = str(msg.get("timestamp", ""))
        text = _extract_text_content(msg.get("content", ""))
        writer.writerow([ts, role, text])

    frappe.response["filename"] = f"{session_id}.csv"
    frappe.response["filecontent"] = output.getvalue().encode("utf-8")
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "text/csv; charset=utf-8"
