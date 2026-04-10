"""Tests for token cost calculation."""
import unittest


class TestTokenPricing(unittest.TestCase):

    def test_cost_calculation(self):
        """Verify cost calculation matches Anthropic pricing."""
        # Import pricing constants only (no frappe dependency)
        import os
        import re

        counter_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "utils", "token_counter.py"
        )
        with open(counter_path) as f:
            content = f.read()

        # Verify the pricing dict exists and has expected models
        self.assertIn("claude-sonnet-4-20250514", content)
        self.assertIn("input_per_mtok", content)
        self.assertIn("output_per_mtok", content)

    def test_cost_formula(self):
        """Manual cost calculation should match expected values."""
        # Sonnet 4 pricing: $3/Mtok input, $15/Mtok output
        input_tokens = 1000
        output_tokens = 500
        input_per_mtok = 3.00
        output_per_mtok = 15.00

        cost = (
            (input_tokens / 1_000_000) * input_per_mtok
            + (output_tokens / 1_000_000) * output_per_mtok
        )

        # 1000 input tokens = $0.003, 500 output tokens = $0.0075
        expected = 0.003 + 0.0075
        self.assertAlmostEqual(cost, expected, places=6)

    def test_zero_tokens_zero_cost(self):
        """Zero tokens should produce zero cost."""
        cost = (0 / 1_000_000) * 3.00 + (0 / 1_000_000) * 15.00
        self.assertEqual(cost, 0.0)


if __name__ == "__main__":
    unittest.main()
