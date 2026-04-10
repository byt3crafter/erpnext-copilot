import frappe
from frappe.model.document import Document


class AIChatSession(Document):
    pass


def has_permission(doc, ptype, user):
    if ptype == "read" and doc.user == user:
        return True
    if "System Manager" in frappe.get_roles(user):
        return True
    return False
