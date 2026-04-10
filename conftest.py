"""Pytest configuration for running tests outside of a Frappe bench.

This makes the inner erpnext_ai_bots/ package importable as 'erpnext_ai_bots'
by adding it to sys.path before tests run.
"""
import sys
import os

# The inner package directory (erpnext_ai_bots/erpnext_ai_bots/) needs to
# be importable as 'erpnext_ai_bots'. We achieve this by inserting the
# app root into sys.path, which is the standard Frappe app layout.
app_root = os.path.dirname(os.path.abspath(__file__))

# Remove any existing erpnext_ai_bots entries to avoid shadowing
sys.path = [p for p in sys.path if os.path.basename(p) != "erpnext_ai_bots"]

# Insert app root so 'import erpnext_ai_bots' finds the inner package
sys.path.insert(0, app_root)
