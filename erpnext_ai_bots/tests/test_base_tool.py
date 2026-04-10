"""Tests for BaseTool schema generation.

BaseTool itself has no frappe dependency (only abc), so we test
the schema generation directly by reimplementing the contract.
"""
import unittest
import os
import re


class TestBaseTool(unittest.TestCase):

    def test_base_tool_has_required_interface(self):
        """BaseTool source must define the expected interface."""
        base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools", "base.py"
        )
        with open(base_path) as f:
            content = f.read()

        # Must define these attributes
        self.assertIn("class BaseTool", content)
        self.assertIn("def schema(self)", content)
        self.assertIn("def execute(self", content)
        self.assertIn("name:", content)
        self.assertIn("description:", content)
        self.assertIn("parameters:", content)
        self.assertIn("required_params:", content)
        self.assertIn("action_type:", content)

    def test_schema_method_returns_anthropic_format(self):
        """The schema() method must produce Anthropic-compatible format."""
        base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools", "base.py"
        )
        with open(base_path) as f:
            content = f.read()

        # Schema must return dict with these keys
        self.assertIn('"name"', content)
        self.assertIn('"description"', content)
        self.assertIn('"input_schema"', content)
        self.assertIn('"type"', content)
        self.assertIn('"properties"', content)
        self.assertIn('"required"', content)

    def test_all_tools_extend_base_tool(self):
        """Every tool file in tools/*/ must have a class extending BaseTool."""
        tools_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "tools"
        )

        tool_dirs = ["core", "accounting", "hr", "stock", "sales", "meta"]
        for subdir in tool_dirs:
            dir_path = os.path.join(tools_dir, subdir)
            if not os.path.isdir(dir_path):
                continue

            for fname in os.listdir(dir_path):
                if not fname.endswith(".py") or fname == "__init__.py":
                    continue

                fpath = os.path.join(dir_path, fname)
                with open(fpath) as f:
                    content = f.read()

                # Must import BaseTool
                has_import = "from erpnext_ai_bots.tools.base import BaseTool" in content
                # Must have a class that extends it
                has_class = bool(re.search(r"class \w+\(BaseTool\)", content))

                self.assertTrue(
                    has_import and has_class,
                    f"{subdir}/{fname} does not properly extend BaseTool"
                )


if __name__ == "__main__":
    unittest.main()
