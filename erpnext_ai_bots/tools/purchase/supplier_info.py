import frappe
from erpnext_ai_bots.tools.base import BaseTool


class GetSupplierInfoTool(BaseTool):
    name = "purchase.get_supplier_info"
    description = (
        "Look up supplier info with fuzzy matching. "
        "Pass any part of the supplier name or ID — the tool searches by exact match, "
        "partial match on supplier_name, partial match on ID, and individual words. "
        "Returns full supplier details. "
        "Without a supplier name, lists up to 20 suppliers optionally filtered by supplier_group."
    )
    parameters = {
        "supplier": {
            "type": "string",
            "description": (
                "Supplier document name or supplier_name to look up. "
                "Omit to list suppliers (optionally narrowed by supplier_group)."
            ),
        },
        "supplier_group": {
            "type": "string",
            "description": "Supplier Group to filter by when listing (e.g. 'Services', 'Raw Material').",
        },
    }
    required_params = []
    action_type = "Read"
    required_doctype = "Supplier"
    required_ptype = "read"

    def execute(self, supplier=None, supplier_group=None, **kwargs):
        frappe.has_permission("Supplier", ptype="read", throw=True)

        if supplier:
            # Exact doc name
            if frappe.db.exists("Supplier", supplier):
                doc = frappe.get_doc("Supplier", supplier)
            else:
                # Partial match on supplier_name
                matches = frappe.get_all(
                    "Supplier",
                    filters={"supplier_name": ["like", f"%{supplier}%"]},
                    fields=["name", "supplier_name"],
                    limit_page_length=5,
                )
                # Partial match on ID
                if not matches:
                    matches = frappe.get_all(
                        "Supplier",
                        filters={"name": ["like", f"%{supplier}%"]},
                        fields=["name", "supplier_name"],
                        limit_page_length=5,
                    )
                # Word-by-word fallback
                if not matches and " " in supplier:
                    for word in supplier.split():
                        if len(word) < 3:
                            continue
                        matches = frappe.get_all(
                            "Supplier",
                            filters={"supplier_name": ["like", f"%{word}%"]},
                            fields=["name", "supplier_name"],
                            limit_page_length=5,
                        )
                        if not matches:
                            matches = frappe.get_all(
                                "Supplier",
                                filters={"name": ["like", f"%{word}%"]},
                                fields=["name", "supplier_name"],
                                limit_page_length=5,
                            )
                        if matches:
                            break

                if not matches:
                    return {
                        "supplier": None,
                        "message": f"No supplier found matching '{supplier}'. Try a different name or spelling.",
                    }
                if len(matches) > 1:
                    return {
                        "supplier": None,
                        "close_matches": [
                            {"id": m["name"], "name": m.get("supplier_name", m["name"])}
                            for m in matches
                        ],
                        "message": f"Multiple suppliers match '{supplier}'. Which one did you mean?",
                    }
                doc = frappe.get_doc("Supplier", matches[0]["name"])

            # Get outstanding payables for this supplier
            outstanding = self._get_outstanding(doc.name)

            return {
                "supplier": {
                    "name": doc.name,
                    "supplier_name": doc.supplier_name,
                    "supplier_group": doc.supplier_group,
                    "supplier_type": doc.supplier_type,
                    "country": doc.country,
                    "default_currency": doc.default_currency,
                    "mobile_no": doc.mobile_no,
                    "email_id": doc.email_id,
                    "outstanding_amount": outstanding,
                },
            }

        # List mode
        filters = {}
        if supplier_group:
            filters["supplier_group"] = supplier_group

        suppliers = frappe.get_all(
            "Supplier",
            filters=filters,
            fields=[
                "name",
                "supplier_name",
                "supplier_group",
                "supplier_type",
                "country",
            ],
            order_by="supplier_name asc",
            limit_page_length=20,
        )

        return {
            "suppliers": suppliers,
            "count": len(suppliers),
        }

    def _get_outstanding(self, supplier: str) -> float:
        result = frappe.get_all(
            "Purchase Invoice",
            filters={"supplier": supplier, "docstatus": 1, "outstanding_amount": [">", 0]},
            fields=["outstanding_amount"],
        )
        return sum(row.get("outstanding_amount") or 0.0 for row in result)
