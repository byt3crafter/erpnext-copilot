import frappe

# Pricing per million tokens (update when Anthropic changes pricing)
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_creation_per_mtok": 3.75,
        "cache_read_per_mtok": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_mtok": 0.80,
        "output_per_mtok": 4.00,
        "cache_creation_per_mtok": 1.00,
        "cache_read_per_mtok": 0.08,
    },
}

DEFAULT_PRICING = {
    "input_per_mtok": 3.00,
    "output_per_mtok": 15.00,
    "cache_creation_per_mtok": 3.75,
    "cache_read_per_mtok": 0.30,
}


class TokenTracker:
    """Tracks token usage and cost for a single session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.total_input = 0
        self.total_output = 0
        self.total_cost = 0.0

    def record(self, input_tokens: int, output_tokens: int,
               model: str, cache_creation_tokens: int = 0,
               cache_read_tokens: int = 0, is_subagent: bool = False):
        """Record a single API call's token usage."""
        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

        cost = (
            (input_tokens / 1_000_000) * pricing["input_per_mtok"]
            + (output_tokens / 1_000_000) * pricing["output_per_mtok"]
            + (cache_creation_tokens / 1_000_000) * pricing["cache_creation_per_mtok"]
            + (cache_read_tokens / 1_000_000) * pricing["cache_read_per_mtok"]
        )

        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_cost += cost

        # Token tracking is best-effort — never crash the orchestrator
        try:
            if not frappe.db.exists("AI Chat Session", self.session_id):
                return

            session = frappe.get_cached_doc("AI Chat Session", self.session_id)

            frappe.get_doc({
                "doctype": "AI Usage Record",
                "session": self.session_id,
                "user": session.user,
                "company": session.company,
                "timestamp": frappe.utils.now_datetime(),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cost_usd": cost,
                "is_subagent": is_subagent,
                "request_type": "Subagent" if is_subagent else "Chat",
            }).insert(ignore_permissions=True)
        except Exception:
            # Log but don't crash — the AI response is more important
            frappe.log_error(title="Token tracking failed", message=frappe.get_traceback())
        frappe.db.commit()


def cleanup_old_usage_records():
    """Scheduled daily: delete usage records older than 90 days."""
    cutoff = frappe.utils.add_days(frappe.utils.today(), -90)
    old_records = frappe.get_all(
        "AI Usage Record",
        filters={"timestamp": ["<", cutoff]},
        fields=["name"],
        limit_page_length=1000,
    )
    for r in old_records:
        frappe.delete_doc("AI Usage Record", r.name, force=True)
    if old_records:
        frappe.db.commit()
