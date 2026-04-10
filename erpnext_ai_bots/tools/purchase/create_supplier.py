import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateSupplierTool(BaseTool):
    name = "purchase.create_supplier"
    description = (
        "Create a new supplier in ERPNext with optional contact details. "
        "Automatically creates linked Contact and Address records when email, "
        "phone, or address fields are provided. "
        "Before creating, checks for existing suppliers with a similar name and "
        "warns if a likely duplicate is found."
    )
    parameters = {
        "supplier_name": {
            "type": "string",
            "description": "Supplier name (required)",
        },
        "supplier_group": {
            "type": "string",
            "description": "Supplier group. Default: All Supplier Groups",
        },
        "supplier_type": {
            "type": "string",
            "description": "Individual or Company. Default: Company",
        },
        "email": {
            "type": "string",
            "description": "Email address (creates a Contact)",
        },
        "phone": {
            "type": "string",
            "description": "Phone number (creates a Contact)",
        },
        "mobile": {
            "type": "string",
            "description": "Mobile number",
        },
        "contact_person": {
            "type": "string",
            "description": "Contact person full name",
        },
        "address_line1": {
            "type": "string",
            "description": "Street address line 1",
        },
        "city": {
            "type": "string",
            "description": "City",
        },
        "country": {
            "type": "string",
            "description": "Country. Default: Botswana",
        },
    }
    required_params = ["supplier_name"]
    action_type = "Create"
    required_ptype = "create"
    required_doctype = "Supplier"

    def execute(
        self,
        supplier_name,
        supplier_group=None,
        supplier_type=None,
        email=None,
        phone=None,
        mobile=None,
        contact_person=None,
        address_line1=None,
        city=None,
        country=None,
        **kwargs,
    ):
        frappe.has_permission("Supplier", ptype="create", throw=True)

        # ── Duplicate check ───────────────────────────────────────────────────
        existing = frappe.get_all(
            "Supplier",
            filters={"supplier_name": ["like", f"%{supplier_name}%"]},
            fields=["name", "supplier_name"],
            limit_page_length=3,
        )
        if not existing:
            existing = frappe.get_all(
                "Supplier",
                filters={"name": ["like", f"%{supplier_name}%"]},
                fields=["name", "supplier_name"],
                limit_page_length=3,
            )

        if existing:
            return {
                "created": False,
                "warning": "duplicate_risk",
                "message": (
                    f"A supplier with a similar name already exists. "
                    f"Please confirm you want to create a new one."
                ),
                "close_matches": [
                    {"id": s["name"], "name": s.get("supplier_name", s["name"])}
                    for s in existing
                ],
            }

        # ── Resolve defaults ──────────────────────────────────────────────────
        resolved_group = supplier_group or "All Supplier Groups"
        resolved_type = supplier_type or "Company"

        # ── Create Supplier ───────────────────────────────────────────────────
        supplier_doc = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": supplier_name,
                "supplier_group": resolved_group,
                "supplier_type": resolved_type,
            }
        )
        supplier_doc.insert(ignore_permissions=False)
        frappe.db.commit()

        result = {
            "created": True,
            "supplier": supplier_doc.name,
            "supplier_name": supplier_doc.supplier_name,
            "supplier_group": supplier_doc.supplier_group,
            "supplier_type": supplier_doc.supplier_type,
            "contact_created": False,
            "address_created": False,
        }

        # ── Create Contact (if email/phone/mobile provided) ───────────────────
        if email or phone or mobile:
            contact_name = contact_person or supplier_name

            name_parts = contact_name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            contact_doc = frappe.get_doc(
                {
                    "doctype": "Contact",
                    "first_name": first_name,
                    "last_name": last_name,
                    "links": [
                        {
                            "link_doctype": "Supplier",
                            "link_name": supplier_doc.name,
                        }
                    ],
                }
            )

            if email:
                contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})

            if phone:
                contact_doc.append(
                    "phone_nos", {"phone": phone, "is_primary_phone": 1}
                )

            if mobile:
                contact_doc.append(
                    "phone_nos",
                    {"phone": mobile, "is_primary_mobile_no": 1},
                )

            contact_doc.insert(ignore_permissions=False)
            frappe.db.commit()

            result["contact_created"] = True
            result["contact"] = contact_doc.name

        # ── Create Address (if address_line1 or city provided) ────────────────
        if address_line1 or city:
            resolved_country = country or "Botswana"
            address_doc = frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": supplier_name,
                    "address_type": "Billing",
                    "address_line1": address_line1 or "",
                    "city": city or "",
                    "country": resolved_country,
                    "links": [
                        {
                            "link_doctype": "Supplier",
                            "link_name": supplier_doc.name,
                        }
                    ],
                }
            )
            address_doc.insert(ignore_permissions=False)
            frappe.db.commit()

            result["address_created"] = True
            result["address"] = address_doc.name

        return result
