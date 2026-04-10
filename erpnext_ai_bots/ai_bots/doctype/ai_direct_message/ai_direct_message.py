import frappe
from frappe.model.document import Document


class AIDirectMessage(Document):
    pass


def has_permission(doc, ptype, user):
    """Users can read messages they sent or received."""
    if ptype == "read" and (doc.from_user == user or doc.to_user == user):
        return True
    if "System Manager" in frappe.get_roles(user):
        return True
    return False
