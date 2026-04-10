import frappe
import json
from frappe import _


@frappe.whitelist()
def get_company_users(company: str = None):
    """Get users who have permission for a given company.

    Uses User Permission (allow=Company) to filter users.
    Falls back to all enabled users if no company filter or no User Permission records.
    Excludes Administrator and Guest. Excludes the current user.
    """
    current_user = frappe.session.user

    if not company:
        company = frappe.defaults.get_user_default("company", current_user)

    users = []

    if company:
        # Get users with explicit User Permission for this company
        permitted_users = frappe.get_all(
            "User Permission",
            filters={"allow": "Company", "for_value": company},
            pluck="user",
        )
        # Always include users with System Manager role (they see all companies)
        sys_managers = frappe.get_all(
            "Has Role",
            filters={"role": "System Manager", "parenttype": "User"},
            pluck="parent",
        )
        all_allowed = list(set(permitted_users + sys_managers))

        # Remove excluded users from the allowed set
        excluded = {"Administrator", "Guest", current_user}
        all_allowed = [u for u in all_allowed if u not in excluded]

        if all_allowed:
            users = frappe.get_all(
                "User",
                filters={
                    "name": ["in", all_allowed],
                    "enabled": 1,
                },
                fields=["name", "full_name", "user_image"],
                order_by="full_name asc",
                limit_page_length=100,
            )

    # Fallback: if no company-based results, return all enabled desk users
    if not users:
        users = frappe.get_all(
            "User",
            filters={
                "enabled": 1,
                "user_type": "System User",
                "name": ["not in", ["Administrator", "Guest", current_user]],
            },
            fields=["name", "full_name", "user_image"],
            order_by="full_name asc",
            limit_page_length=100,
        )

    # Enrich with online status — check who has an active session
    online_users = set()
    try:
        active_sessions = frappe.db.sql("""
            SELECT DISTINCT user FROM `tabSessions`
            WHERE user NOT IN ('Guest', 'Administrator')
              AND TIMESTAMPDIFF(SECOND, lastupdate, NOW()) < 300
        """, pluck="user")
        online_users = set(active_sessions)
    except Exception:
        pass

    for u in users:
        u["is_online"] = u["name"] in online_users

    # Sort: online users first, then alphabetical
    users.sort(key=lambda u: (not u["is_online"], (u.get("full_name") or u["name"]).lower()))

    return users


@frappe.whitelist()
def forward_message(session_id: str, message_index: int, to_user: str, note: str = ""):
    """Forward a message from an AI chat session to another user as a DM.

    Args:
        session_id: The AI Chat Session containing the message
        message_index: Index of the message in messages_json array
        to_user: Target user email
        note: Optional note from the sender
    """
    user = frappe.session.user
    message_index = int(message_index)

    # Verify session ownership
    session = frappe.get_doc("AI Chat Session", session_id)
    if session.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Access denied"), frappe.PermissionError)

    # Extract the message — filter same way as frontend
    messages = json.loads(session.messages_json or "[]")
    visible = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            continue
        c = m.get("content", "")
        if isinstance(c, str) and c.strip():
            visible.append(m)
        elif isinstance(c, list) and any(
            isinstance(b, dict) and b.get("type") == "text" and b.get("text")
            for b in c
        ):
            visible.append(m)

    if message_index < 0 or message_index >= len(visible):
        frappe.throw(_("Invalid message index"))

    msg = visible[message_index]
    content = msg.get("content", "")
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = "\n".join(filter(None, parts))
    elif not isinstance(content, str):
        content = str(content)

    role_label = "You" if msg.get("role") == "user" else "AI Assistant"
    if note:
        forwarded_text = f"{note}\n\n--- Forwarded from {role_label} ---\n\n{content}"
    else:
        forwarded_text = f"--- Forwarded from {role_label} ---\n\n{content}"

    # Create DM
    dm = frappe.get_doc({
        "doctype": "AI Direct Message",
        "from_user": user,
        "to_user": to_user,
        "company": session.company,
        "message": forwarded_text,
        "message_type": "forward",
        "forwarded_from_session": session_id,
        "forwarded_from_index": message_index,
    })
    dm.insert(ignore_permissions=True)
    frappe.db.commit()

    # Real-time notification to the target user
    frappe.publish_realtime(
        "ai_dm_new",
        {
            "from_user": user,
            "from_name": frappe.db.get_value("User", user, "full_name") or user,
            "message": forwarded_text[:200],
            "dm_id": dm.name,
        },
        user=to_user,
    )

    return {"status": "forwarded", "dm_id": dm.name}


@frappe.whitelist()
def send_dm(to_user: str, message: str, reply_to: str = None, company: str = None):
    """Send a direct message to another user.

    Args:
        to_user: Target user email
        message: Message text
        reply_to: Optional AI Direct Message name to reply to
        company: Optional company context
    """
    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    if to_user == user:
        frappe.throw(_("Cannot send a message to yourself"))

    if not company:
        company = frappe.defaults.get_user_default("company", user)

    dm = frappe.get_doc({
        "doctype": "AI Direct Message",
        "from_user": user,
        "to_user": to_user,
        "company": company,
        "message": message,
        "message_type": "text",
        "reply_to": reply_to,
    })
    dm.insert(ignore_permissions=True)
    frappe.db.commit()

    # Real-time notification
    frappe.publish_realtime(
        "ai_dm_new",
        {
            "from_user": user,
            "from_name": frappe.db.get_value("User", user, "full_name") or user,
            "message": message[:200],
            "dm_id": dm.name,
            "reply_to": reply_to,
        },
        user=to_user,
    )

    return {
        "dm_id": dm.name,
        "creation": str(dm.creation),
    }


@frappe.whitelist()
def get_dm_conversations(company: str = None):
    """Get list of users the current user has DM conversations with.

    Returns a list of users with the latest message preview and unread count.
    """
    user = frappe.session.user

    # Get all DMs involving the current user
    all_dms = frappe.db.sql("""
        SELECT
            CASE WHEN from_user = %(user)s THEN to_user ELSE from_user END AS other_user,
            message,
            creation,
            is_read,
            from_user
        FROM `tabAI Direct Message`
        WHERE from_user = %(user)s OR to_user = %(user)s
        ORDER BY creation DESC
    """, {"user": user}, as_dict=True)

    # Group by other_user, take latest message + count unread
    conversations = {}
    for dm in all_dms:
        other = dm.other_user
        if other not in conversations:
            conversations[other] = {
                "user": other,
                "last_message": dm.message[:100] if dm.message else "",
                "last_message_at": str(dm.creation),
                "unread_count": 0,
                "is_from_me": dm.from_user == user,
            }
        # Count unread (messages TO me that are unread)
        if dm.from_user != user and not dm.is_read:
            conversations[other]["unread_count"] += 1

    # Enrich with user full_name and avatar
    result = []
    for other_user, conv in conversations.items():
        user_info = frappe.db.get_value(
            "User", other_user, ["full_name", "user_image"], as_dict=True
        )
        if user_info:
            conv["full_name"] = user_info.full_name or other_user
            conv["user_image"] = user_info.user_image
        else:
            conv["full_name"] = other_user
            conv["user_image"] = None
        result.append(conv)

    # Enrich with online status
    try:
        active_sessions = frappe.db.sql("""
            SELECT DISTINCT user FROM `tabSessions`
            WHERE user NOT IN ('Guest', 'Administrator')
              AND TIMESTAMPDIFF(SECOND, lastupdate, NOW()) < 300
        """, pluck="user")
        online_set = set(active_sessions)
        for conv in result:
            conv["is_online"] = conv["user"] in online_set
    except Exception:
        for conv in result:
            conv["is_online"] = False

    # Sort by last_message_at descending
    result.sort(key=lambda x: x["last_message_at"], reverse=True)
    return result


@frappe.whitelist()
def get_dm_history(other_user: str, limit: int = 50, offset: int = 0):
    """Get DM history between current user and another user."""
    user = frappe.session.user
    limit = min(int(limit), 100)
    offset = int(offset)

    messages = frappe.get_all(
        "AI Direct Message",
        filters=[
            ["from_user", "in", [user, other_user]],
            ["to_user", "in", [user, other_user]],
        ],
        fields=[
            "name", "from_user", "to_user", "message", "message_type",
            "reply_to", "forwarded_from_session", "is_read", "creation",
        ],
        order_by="creation asc",
        limit_page_length=limit,
        limit_start=offset,
    )

    # Enrich reply_to with the replied message preview
    for msg in messages:
        if msg.reply_to:
            reply_msg = frappe.db.get_value(
                "AI Direct Message", msg.reply_to,
                ["from_user", "message"], as_dict=True,
            )
            if reply_msg:
                msg["reply_preview"] = reply_msg.message[:100] if reply_msg.message else ""
                msg["reply_from"] = reply_msg.from_user

    return messages


@frappe.whitelist()
def mark_dm_read(other_user: str):
    """Mark all DMs from other_user to current user as read."""
    user = frappe.session.user
    frappe.db.sql("""
        UPDATE `tabAI Direct Message`
        SET is_read = 1, read_at = NOW()
        WHERE from_user = %(other)s AND to_user = %(user)s AND is_read = 0
    """, {"other": other_user, "user": user})
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def get_unread_dm_count():
    """Get total unread DM count for the current user."""
    user = frappe.session.user
    count = frappe.db.count(
        "AI Direct Message",
        filters={"to_user": user, "is_read": 0},
    )
    return {"count": count}


@frappe.whitelist()
def get_ai_name():
    """Get the configured AI assistant name."""
    try:
        name = frappe.db.get_single_value("AI Bot Settings", "ai_name")
    except Exception:
        name = None
    return {"ai_name": name or "AI Oracle"}


@frappe.whitelist()
def ask_ai_in_dm(question: str, to_user: str, company: str = None):
    """Invoke the AI agent from within a DM conversation.

    The user types @ai <question> in a DM. This endpoint:
    1. Creates a hidden AI Chat Session for the question
    2. Runs the orchestrator
    3. Posts the AI response as a DM from AI to both users in the conversation

    The AI response is streamed back via Socket.IO as ai_dm_ai_response.
    """
    user = frappe.session.user

    if not question or not question.strip():
        frappe.throw(_("Question cannot be empty"))

    if not company:
        company = frappe.defaults.get_user_default("company", user)

    ai_name = frappe.db.get_single_value("AI Bot Settings", "ai_name") or "AI Oracle"

    # Post the user's @ai message as a DM visible to both
    user_dm = frappe.get_doc({
        "doctype": "AI Direct Message",
        "from_user": user,
        "to_user": to_user,
        "company": company,
        "message": f"@{ai_name} {question}",
        "message_type": "text",
    })
    user_dm.insert(ignore_permissions=True)
    frappe.db.commit()

    # Notify the other user of the @ai question
    frappe.publish_realtime(
        "ai_dm_new",
        {
            "from_user": user,
            "from_name": frappe.db.get_value("User", user, "full_name") or user,
            "message": f"@{ai_name} {question}"[:200],
            "dm_id": user_dm.name,
        },
        user=to_user,
    )

    # Enqueue the AI processing in background
    frappe.enqueue(
        "erpnext_ai_bots.api.messaging._process_ai_dm",
        queue="default",
        timeout=300,
        is_async=True,
        user=user,
        to_user=to_user,
        question=question,
        company=company,
        ai_name=ai_name,
    )

    return {"status": "processing", "dm_id": user_dm.name}


def _process_ai_dm(user, to_user, question, company, ai_name):
    """Background job: run AI agent and post response as DM.

    For simple conversational messages (no ERPNext data needed), uses a
    lightweight direct LLM call. For complex queries, uses the full orchestrator.
    """
    frappe.set_user(user)

    # Try lightweight direct call first for simple messages
    response = _try_lightweight_ai(question, user, company, ai_name)
    if response:
        _post_ai_dm_response(user, to_user, company, ai_name, response)
        return

    # Fall back to full orchestrator for complex queries
    session = frappe.get_doc({
        "doctype": "AI Chat Session",
        "user": user,
        "company": company,
        "status": "Active",
        "title": f"DM AI: {question[:80]}",
        "category": "General",
        "messages_json": "[]",
        "model_used": frappe.db.get_single_value("AI Bot Settings", "model_name") or "",
    })
    session.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        from erpnext_ai_bots.agent.orchestrator import run_orchestrator
        run_orchestrator(
            user=user,
            session_id=session.name,
            message=question,
            company=company,
        )
    except Exception as e:
        ai_response = f"Sorry, I encountered an error: {str(e)}"
        _post_ai_dm_response(user, to_user, company, ai_name, ai_response)
        return

    session.reload()
    messages = json.loads(session.messages_json or "[]")
    ai_msgs = [m for m in messages if m.get("role") == "assistant"]
    if ai_msgs:
        content = ai_msgs[-1].get("content", "")
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(filter(None, parts))
        ai_response = content or "I processed your request but had no text response."
    else:
        ai_response = "I couldn't generate a response. Please try again."

    _post_ai_dm_response(user, to_user, company, ai_name, ai_response)


def _try_lightweight_ai(question, user, company, ai_name):
    """Attempt a fast, direct LLM call without tools for simple messages.

    Returns the response string if successful, or None to fall back to the
    full orchestrator.
    """
    # Detect if this is a simple conversational message (no ERPNext data needed)
    q_lower = question.lower().strip()
    data_keywords = [
        "invoice", "payment", "stock", "item", "customer", "supplier",
        "report", "balance", "ledger", "quotation", "order", "employee",
        "salary", "leave", "attendance", "create", "update", "delete",
        "submit", "cancel", "show me", "list", "how much", "how many",
        "what is the", "what are the", "get", "find", "search", "run",
        "schedule", "remind", "email", "send", "chart", "graph",
        "analyze", "file", "image", "sql", "query",
    ]
    needs_tools = any(kw in q_lower for kw in data_keywords)
    if needs_tools:
        return None

    settings = frappe.get_cached_doc("AI Bot Settings")
    provider = settings.provider or "Anthropic"

    user_full_name = frappe.db.get_value("User", user, "full_name") or user

    system_msg = (
        f"You are {ai_name}, a friendly AI assistant at {company or 'the company'}. "
        f"You are chatting with {user_full_name} in a direct message. "
        f"Keep responses concise, friendly, and natural. "
        f"If the user asks about ERPNext data, invoices, reports, stock, or anything "
        f"that requires database access, reply with exactly: [NEEDS_TOOLS] "
        f"so the system can route to the full agent."
    )

    try:
        if provider == "Anthropic":
            import anthropic
            api_key = settings.get_password("api_key")
            if not api_key:
                return None
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=settings.model_name or "claude-sonnet-4-20250514",
                max_tokens=512,
                system=system_msg,
                messages=[{"role": "user", "content": question}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            if "[NEEDS_TOOLS]" in text:
                return None
            return text.strip() if text.strip() else None

        elif provider == "OpenAI (ChatGPT OAuth)":
            from erpnext_ai_bots.licensing.openai_codex import CodexClient
            codex = CodexClient()
            response = codex.responses.create(
                model=settings.model_name or "gpt-4.1",
                instructions=system_msg,
                input=question,
                max_output_tokens=512,
            )
            text = ""
            for item in response.output:
                if hasattr(item, "content"):
                    for block in item.content:
                        if hasattr(block, "text"):
                            text += block.text
            if "[NEEDS_TOOLS]" in text:
                return None
            return text.strip() if text.strip() else None

    except Exception:
        return None

    return None


def _post_ai_dm_response(user, to_user, company, ai_name, response):
    """Post the AI response as DMs to both users in the conversation."""
    # Post AI response as a DM from the requesting user (marked as AI)
    ai_dm = frappe.get_doc({
        "doctype": "AI Direct Message",
        "from_user": user,
        "to_user": to_user,
        "company": company,
        "message": f"**{ai_name}:**\n{response}",
        "message_type": "text",
    })
    ai_dm.insert(ignore_permissions=True)
    frappe.db.commit()

    full_name = frappe.db.get_value("User", user, "full_name") or user

    # Notify both users via real-time
    for target_user in [user, to_user]:
        frappe.publish_realtime(
            "ai_dm_ai_response",
            {
                "from_user": user,
                "to_user": to_user,
                "ai_name": ai_name,
                "message": response[:500],
                "dm_id": ai_dm.name,
            },
            user=target_user,
        )
