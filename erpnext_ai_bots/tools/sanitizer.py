import frappe
import json
import re
from typing import List, Tuple

# Fields NEVER allowed via AI tools, regardless of whitelist
GLOBALLY_BLOCKED_FIELDS = {
    "password", "api_key", "api_secret", "secret", "token",
    "oauth_token", "session_id", "two_factor_secret",
    "login_before", "login_after", "reset_password_key",
    "last_password_reset_date", "restrict_ip",
}

# DocTypes NEVER accessible via AI tools
BLOCKED_DOCTYPES = {
    "User", "User Permission", "Role", "Role Profile",
    "OAuth Client", "OAuth Bearer Token", "OAuth Authorization Code",
    "Session Default Settings", "System Settings",
    "Scheduled Job Log", "Error Log", "Activity Log",
    "AI Bot Settings",  # Prevent self-modification
}


class InputSanitizer:
    """Sanitizes tool inputs before execution.

    1. Blocks access to forbidden DocTypes
    2. Strips fields not in whitelist (for write operations)
    3. Removes globally blocked fields
    4. Validates field names contain only safe characters
    5. Limits string lengths to prevent memory bombs
    """

    def __init__(self):
        self._whitelist_cache = {}

    def sanitize(self, tool_name: str, tool_input: dict) -> Tuple[dict, List[str]]:
        """Sanitize tool input. Returns (sanitized_input, blocked_fields)."""
        blocked_fields = []

        # 1. Check for blocked DocTypes
        doctype = tool_input.get("doctype", "")
        if doctype in BLOCKED_DOCTYPES:
            frappe.throw(
                f"Access to DocType '{doctype}' is not allowed via AI tools.",
                frappe.PermissionError,
            )

        # Also check the settings blocklist
        settings = frappe.get_cached_doc("AI Bot Settings")
        if settings.blocked_doctypes:
            extra_blocked = json.loads(settings.blocked_doctypes)
            if doctype in extra_blocked:
                frappe.throw(
                    f"Access to DocType '{doctype}' is blocked by admin configuration.",
                    frappe.PermissionError,
                )

        # 2. Validate field names (prevent injection via field names)
        if "fields" in tool_input and isinstance(tool_input["fields"], list):
            safe_fields = []
            for f in tool_input["fields"]:
                if self._is_safe_field_name(f):
                    if f.lower() not in GLOBALLY_BLOCKED_FIELDS:
                        safe_fields.append(f)
                    else:
                        blocked_fields.append(f)
                else:
                    blocked_fields.append(f)
            tool_input["fields"] = safe_fields

        # 3. For write operations, apply field whitelisting
        is_write = any(w in tool_name for w in ["create", "update", "submit"])
        if is_write and doctype and "values" in tool_input:
            tool_input["values"], write_blocked = self._apply_write_whitelist(
                doctype, tool_input["values"]
            )
            blocked_fields.extend(write_blocked)

        # 4. Limit string lengths
        tool_input = self._limit_string_lengths(tool_input)

        # 5. Sanitize filter values
        if "filters" in tool_input and isinstance(tool_input["filters"], dict):
            tool_input["filters"] = self._sanitize_filters(
                doctype, tool_input["filters"]
            )

        return tool_input, blocked_fields

    def _is_safe_field_name(self, name: str) -> bool:
        """Field names must be alphanumeric + underscores only."""
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))

    def _apply_write_whitelist(
        self, doctype: str, values: dict
    ) -> Tuple[dict, List[str]]:
        """For write ops, only allow whitelisted fields."""
        settings = frappe.get_cached_doc("AI Bot Settings")
        if not settings.enable_field_whitelisting:
            blocked = []
            clean = {}
            for k, v in values.items():
                if k.lower() in GLOBALLY_BLOCKED_FIELDS:
                    blocked.append(k)
                else:
                    clean[k] = v
            return clean, blocked

        whitelist = self._get_whitelist(doctype)
        if not whitelist:
            frappe.throw(
                f"No field whitelist configured for '{doctype}'. "
                "Write operations are blocked until an admin configures one.",
                frappe.PermissionError,
            )

        allowed_fields = set(json.loads(whitelist.writable_fields or "[]"))
        if not allowed_fields:
            frappe.throw(
                f"No writable fields configured for '{doctype}'.",
                frappe.PermissionError,
            )

        blocked = []
        clean = {}
        for k, v in values.items():
            if k in allowed_fields and k.lower() not in GLOBALLY_BLOCKED_FIELDS:
                clean[k] = v
            else:
                blocked.append(k)

        return clean, blocked

    def _get_whitelist(self, doctype: str):
        """Get the AI Field Whitelist config for a DocType, with caching."""
        if doctype not in self._whitelist_cache:
            wl = frappe.db.get_value(
                "AI Field Whitelist",
                {"ref_doctype": doctype},
                ["*"],
                as_dict=True,
            )
            self._whitelist_cache[doctype] = wl
        return self._whitelist_cache[doctype]

    def _sanitize_filters(self, doctype: str, filters: dict) -> dict:
        """Validate that filter keys are valid field names."""
        clean = {}
        for k, v in filters.items():
            if self._is_safe_field_name(k) and k.lower() not in GLOBALLY_BLOCKED_FIELDS:
                clean[k] = v
        return clean

    def _limit_string_lengths(self, data: dict, max_str_len: int = 10000) -> dict:
        """Limit string field lengths to prevent memory/token bombs."""
        clean = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > max_str_len:
                clean[k] = v[:max_str_len]
            elif isinstance(v, dict):
                clean[k] = self._limit_string_lengths(v, max_str_len)
            elif isinstance(v, list):
                clean[k] = [
                    self._limit_string_lengths(item, max_str_len)
                    if isinstance(item, dict)
                    else item
                    for item in v
                ]
            else:
                clean[k] = v
        return clean
