import re
import frappe

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)",
    r"forget\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)",
    r"disregard\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)",
    r"override\s+(system|admin)\s+(prompt|instructions)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*prompt\s*:",
    r"(print|show|display|reveal|output|repeat)\s+(your\s+)?(system\s+)?prompt",
    r"what\s+(is|are)\s+your\s+(system\s+)?instructions",
    r"(admin|root|sudo)\s+mode",
    r"debug\s+mode",
    r"developer\s+mode",
    r"maintenance\s+mode",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def check_prompt_injection(user_message: str):
    """Scan user input for common prompt injection patterns.
    Does NOT block -- logs a warning. The permission layer prevents actual damage.
    """
    settings = frappe.get_cached_doc("AI Bot Settings")
    if not settings.enable_prompt_defense:
        return

    for pattern in COMPILED_PATTERNS:
        match = pattern.search(user_message)
        if match:
            frappe.logger("ai_security").warning(
                f"Potential prompt injection from {frappe.session.user}: "
                f"pattern='{match.group()}' message='{user_message[:200]}...'"
            )

            frappe.get_doc({
                "doctype": "AI Audit Log",
                "user": frappe.session.user,
                "tool_name": "_prompt_defense",
                "tool_input_json": f'{{"message": "{user_message[:500]}"}}',
                "tool_output_json": f'{{"pattern": "{match.group()}"}}',
                "tool_result_status": "SanitizationBlocked",
                "action_type": "Read",
            }).insert(ignore_permissions=True)

            # We do NOT block -- the model's system prompt + permission layer handles it
            return
