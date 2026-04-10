import frappe
from erpnext_ai_bots.tools.base import BaseTool


class CreateCustomerTool(BaseTool):
    name = "sales.create_customer"
    description = (
        "Create a new customer in ERPNext with optional contact details. "
        "Automatically creates linked Contact and Address records when email, "
        "phone, or address fields are provided. "
        "Before creating, checks for existing customers with a similar name and "
        "warns if a likely duplicate is found."
    )
    parameters = {
        "customer_name": {
            "type": "string",
            "description": "Customer name (required)",
        },
        "customer_group": {
            "type": "string",
            "description": "Customer group (e.g. Commercial, Individual). Default: All Customer Groups",
        },
        "territory": {
            "type": "string",
            "description": "Territory. Default: All Territories",
        },
        "customer_type": {
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
            "description": "Contact person full name (for Company type customers)",
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
    required_params = ["customer_name"]
    action_type = "Create"
    required_ptype = "create"
    required_doctype = "Customer"

    def execute(
        self,
        customer_name,
        customer_group=None,
        territory=None,
        customer_type=None,
        email=None,
        phone=None,
        mobile=None,
        contact_person=None,
        address_line1=None,
        city=None,
        country=None,
        **kwargs,
    ):
        frappe.has_permission("Customer", ptype="create", throw=True)

        # ── Duplicate check ───────────────────────────────────────────────────
        existing = frappe.get_all(
            "Customer",
            filters={"customer_name": ["like", f"%{customer_name}%"]},
            fields=["name", "customer_name"],
            limit_page_length=3,
        )
        if not existing:
            # Also check on the doc name (ID) in case customer_name differs
            existing = frappe.get_all(
                "Customer",
                filters={"name": ["like", f"%{customer_name}%"]},
                fields=["name", "customer_name"],
                limit_page_length=3,
            )

        if existing:
            return {
                "created": False,
                "warning": "duplicate_risk",
                "message": (
                    f"A customer with a similar name already exists. "
                    f"Please confirm you want to create a new one."
                ),
                "close_matches": [
                    {"id": c["name"], "name": c.get("customer_name", c["name"])}
                    for c in existing
                ],
            }

        # ── Resolve defaults ──────────────────────────────────────────────────
        resolved_group = customer_group or "All Customer Groups"
        resolved_territory = territory or "All Territories"
        resolved_type = customer_type or "Company"

        # ── Create Customer ───────────────────────────────────────────────────
        customer_doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_group": resolved_group,
                "territory": resolved_territory,
                "customer_type": resolved_type,
            }
        )
        customer_doc.insert(ignore_permissions=False)
        frappe.db.commit()

        result = {
            "created": True,
            "customer": customer_doc.name,
            "customer_name": customer_doc.customer_name,
            "customer_group": customer_doc.customer_group,
            "territory": customer_doc.territory,
            "customer_type": customer_doc.customer_type,
            "contact_created": False,
            "address_created": False,
        }

        # ── Create Contact (if email/phone/mobile provided) ───────────────────
        if email or phone or mobile:
            contact_name = contact_person or customer_name

            # Split into first/last for Contact doctype
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
                            "link_doctype": "Customer",
                            "link_name": customer_doc.name,
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
                    "address_title": customer_name,
                    "address_type": "Billing",
                    "address_line1": address_line1 or "",
                    "city": city or "",
                    "country": resolved_country,
                    "links": [
                        {
                            "link_doctype": "Customer",
                            "link_name": customer_doc.name,
                        }
                    ],
                }
            )
            address_doc.insert(ignore_permissions=False)
            frappe.db.commit()

            result["address_created"] = True
            result["address"] = address_doc.name

        return result
