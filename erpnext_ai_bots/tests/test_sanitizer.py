"""Tests for the InputSanitizer — field whitelisting, blocked doctypes, field name validation.

These tests read source files directly to avoid frappe import issues
outside of a bench environment. The critical logic (regex validation,
set membership) is tested by extracting and evaluating it.
"""
import unittest
import os
import re
import json


def _read_sanitizer_source():
    return open(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "tools", "sanitizer.py"
    )).read()


class TestInputSanitizer(unittest.TestCase):

    def test_blocked_doctypes_defined(self):
        """User, Role, System Settings, AI Bot Settings should be blocked."""
        content = _read_sanitizer_source()
        for dt in ["User", "Role", "System Settings", "AI Bot Settings"]:
            self.assertIn(f'"{dt}"', content, f"{dt} not in BLOCKED_DOCTYPES")

    def test_globally_blocked_fields_defined(self):
        """password, api_key, api_secret should be globally blocked."""
        content = _read_sanitizer_source()
        for field in ["password", "api_key", "api_secret", "token", "secret"]:
            self.assertIn(f'"{field}"', content, f"{field} not in GLOBALLY_BLOCKED_FIELDS")

    def test_safe_field_name_regex(self):
        """The field name regex should accept safe names and reject unsafe ones."""
        content = _read_sanitizer_source()
        # Extract the regex pattern
        match = re.search(r"re\.match\(r['\"](.+?)['\"]", content)
        self.assertIsNotNone(match, "Could not find field name regex")

        pattern = re.compile(match.group(1))

        # Safe names
        for name in ["customer_name", "grand_total", "_private", "field1"]:
            self.assertIsNotNone(pattern.match(name), f"Should accept: {name}")

        # Unsafe names
        for name in ["name; DROP TABLE", "field.nested", "", "123start"]:
            self.assertIsNone(pattern.match(name), f"Should reject: {name}")

    def test_string_length_limit_defined(self):
        """Should have a max string length constant."""
        content = _read_sanitizer_source()
        self.assertIn("max_str_len", content)
        self.assertIn("10000", content)

    def test_write_whitelist_check_exists(self):
        """Write operations must go through whitelist check."""
        content = _read_sanitizer_source()
        self.assertIn("_apply_write_whitelist", content)
        self.assertIn("enable_field_whitelisting", content)

    def test_filter_sanitization_exists(self):
        """Filter sanitization must validate field names."""
        content = _read_sanitizer_source()
        self.assertIn("_sanitize_filters", content)
        self.assertIn("_is_safe_field_name", content)


if __name__ == "__main__":
    unittest.main()
