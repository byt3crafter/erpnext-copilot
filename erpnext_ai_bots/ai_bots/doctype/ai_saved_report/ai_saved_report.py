import frappe
from frappe.model.document import Document


class AISavedReport(Document):
    def before_insert(self):
        if not self.user:
            self.user = frappe.session.user
