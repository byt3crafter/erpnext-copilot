"""Tests for the PermissionGuard tool-to-permission mapping."""
import unittest
import os
import re


class TestPermissions(unittest.TestCase):

    def _load_permission_map(self):
        """Parse TOOL_PERMISSION_MAP from permissions.py without importing frappe."""
        perm_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "guards", "permissions.py"
        )
        with open(perm_path) as f:
            content = f.read()

        # Extract tool names from the map
        entries = re.findall(r'"([a-z]+\.[a-z_]+)":\s*\(', content)
        return entries

    def _load_tool_map_keys(self):
        """Parse tool names from TOOL_MAP in registry.py."""
        registry_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools", "registry.py"
        )
        with open(registry_path) as f:
            content = f.read()

        keys = re.findall(r'"([a-z]+\.[a-z_]+)":\s', content)
        return keys

    def test_every_tool_has_permission_mapping(self):
        """Every tool in TOOL_MAP must have an entry in TOOL_PERMISSION_MAP."""
        tool_keys = set(self._load_tool_map_keys())
        perm_keys = set(self._load_permission_map())

        missing = tool_keys - perm_keys
        self.assertEqual(
            missing, set(),
            f"Tools missing from TOOL_PERMISSION_MAP: {missing}"
        )

    def test_no_orphan_permission_entries(self):
        """Every permission entry should map to a real tool."""
        tool_keys = set(self._load_tool_map_keys())
        perm_keys = set(self._load_permission_map())

        orphans = perm_keys - tool_keys
        self.assertEqual(
            orphans, set(),
            f"Permission entries with no matching tool: {orphans}"
        )


if __name__ == "__main__":
    unittest.main()
