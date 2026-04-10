"""Tests for the ToolRegistry — verify all tool paths resolve."""
import unittest
import importlib
import os


class TestToolRegistry(unittest.TestCase):

    def test_all_tool_map_entries_resolve(self):
        """Every entry in TOOL_MAP should point to an existing file and class."""
        # We can't import frappe-dependent modules, so parse the registry file directly
        registry_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools", "registry.py"
        )

        with open(registry_path) as f:
            content = f.read()

        # Extract all TOOL_MAP values
        import re
        entries = re.findall(r'"(erpnext_ai_bots\.\S+)"', content)

        # Filter to class paths (contain a capital letter for class name)
        class_paths = [e for e in entries if e[0].islower() and "." in e]

        app_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        for class_path in class_paths:
            parts = class_path.split(".")
            # Module path is everything except the last part (class name)
            module_parts = parts[:-1]
            class_name = parts[-1]

            # Convert to file path
            file_path = os.path.join(app_root, *module_parts) + ".py"

            # Check file exists
            self.assertTrue(
                os.path.exists(file_path),
                f"File not found for {class_path}: expected {file_path}"
            )

            # Check class exists in file
            with open(file_path) as f:
                file_content = f.read()

            self.assertIn(
                f"class {class_name}",
                file_content,
                f"Class '{class_name}' not found in {file_path}"
            )

    def test_no_duplicate_tool_names(self):
        """Tool names in TOOL_MAP should be unique."""
        registry_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools", "registry.py"
        )

        with open(registry_path) as f:
            content = f.read()

        import re
        keys = re.findall(r'"([a-z]+\.[a-z_]+)":\s', content)
        self.assertEqual(len(keys), len(set(keys)), f"Duplicate tool names found: {keys}")


if __name__ == "__main__":
    unittest.main()
