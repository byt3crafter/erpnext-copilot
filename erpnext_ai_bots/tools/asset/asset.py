import frappe
from erpnext_ai_bots.tools.base import BaseTool


class AssetTool(BaseTool):
    name = "asset.manage_asset"
    description = (
        "Look up assets, check depreciation schedules, or list assets by category or location. "
        "Actions: 'get' (single asset details), 'list' (with filters), 'depreciation' (schedule for an asset)."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "get, list, or depreciation",
        },
        "asset_name": {
            "type": "string",
            "description": "Asset document name or partial name (for get/depreciation)",
        },
        "asset_category": {
            "type": "string",
            "description": "Asset category filter for list (e.g. Computers, Vehicles, Furniture)",
        },
        "location": {
            "type": "string",
            "description": "Location filter for list (e.g. Office, Warehouse)",
        },
        "status": {
            "type": "string",
            "description": "Draft, Submitted, Partially Depreciated, Fully Depreciated, Scrapped (for list)",
        },
        "company": {
            "type": "string",
            "description": "Company name (optional, defaults to session company)",
        },
        "limit": {
            "type": "integer",
            "description": "Max assets to return for list action (default 20)",
        },
    }
    required_params = ["action"]
    action_type = "Read"
    required_doctype = "Asset"
    required_ptype = "read"

    def execute(self, action, asset_name=None, asset_category=None, location=None,
                status=None, company=None, limit=20, **kwargs):
        action = action.lower().strip()

        if action == "get":
            return self._get(asset_name)
        elif action == "list":
            return self._list(asset_category, location, status, company, limit)
        elif action == "depreciation":
            return self._depreciation(asset_name)
        else:
            frappe.throw(
                f"Unknown action '{action}'. Valid actions are: get, list, depreciation."
            )

    def _get(self, asset_name):
        frappe.has_permission("Asset", ptype="read", throw=True)

        if not asset_name:
            frappe.throw("asset_name is required to look up an asset.")

        if not frappe.db.exists("Asset", asset_name):
            # Fuzzy match on asset_name field
            matches = frappe.get_all(
                "Asset",
                filters={"asset_name": ["like", f"%{asset_name}%"]},
                fields=["name", "asset_name"],
                limit_page_length=5,
            )
            if not matches:
                matches = frappe.get_all(
                    "Asset",
                    filters={"name": ["like", f"%{asset_name}%"]},
                    fields=["name", "asset_name"],
                    limit_page_length=5,
                )
            if not matches:
                return {"asset": None, "message": f"No asset found matching '{asset_name}'."}
            if len(matches) > 1:
                return {
                    "asset": None,
                    "close_matches": [
                        {"id": m["name"], "name": m.get("asset_name", m["name"])}
                        for m in matches
                    ],
                    "message": f"Multiple assets match '{asset_name}'. Which one did you mean?",
                }
            asset_name = matches[0]["name"]

        doc = frappe.get_doc("Asset", asset_name)

        # Current book value
        current_value = doc.value_after_depreciation or doc.gross_purchase_amount

        return {
            "asset": {
                "name": doc.name,
                "asset_name": doc.asset_name,
                "asset_category": doc.asset_category,
                "status": doc.status,
                "company": doc.company,
                "location": doc.location,
                "purchase_date": str(doc.purchase_date) if doc.purchase_date else None,
                "gross_purchase_amount": doc.gross_purchase_amount,
                "current_value": current_value,
                "total_asset_cost": doc.total_asset_cost,
                "depreciation_method": doc.depreciation_method,
                "is_fully_depreciated": doc.is_fully_depreciated,
            }
        }

    def _list(self, asset_category, location, status, company, limit):
        frappe.has_permission("Asset", ptype="read", throw=True)

        limit = min(int(limit or 20), 100)
        filters = {}
        if company or self.company:
            filters["company"] = company or self.company
        if asset_category:
            filters["asset_category"] = ["like", f"%{asset_category}%"]
        if location:
            filters["location"] = ["like", f"%{location}%"]
        if status:
            filters["status"] = status

        assets = frappe.get_all(
            "Asset",
            filters=filters,
            fields=[
                "name",
                "asset_name",
                "asset_category",
                "status",
                "location",
                "purchase_date",
                "gross_purchase_amount",
                "value_after_depreciation",
            ],
            order_by="creation desc",
            limit_page_length=limit,
        )

        total_gross = sum(a.get("gross_purchase_amount") or 0 for a in assets)
        total_book_value = sum(
            (a.get("value_after_depreciation") or a.get("gross_purchase_amount") or 0)
            for a in assets
        )

        return {
            "assets": assets,
            "count": len(assets),
            "total_gross_value": total_gross,
            "total_book_value": total_book_value,
        }

    def _depreciation(self, asset_name):
        frappe.has_permission("Asset", ptype="read", throw=True)

        if not asset_name:
            frappe.throw("asset_name is required to view the depreciation schedule.")

        # Resolve asset (reuse _get logic for fuzzy matching)
        if not frappe.db.exists("Asset", asset_name):
            matches = frappe.get_all(
                "Asset",
                filters={"asset_name": ["like", f"%{asset_name}%"]},
                fields=["name"],
                limit_page_length=1,
            )
            if not matches:
                return {
                    "schedule": None,
                    "message": f"No asset found matching '{asset_name}'.",
                }
            asset_name = matches[0]["name"]

        doc = frappe.get_doc("Asset", asset_name)

        schedule = frappe.get_all(
            "Depreciation Schedule",
            filters={"parent": doc.name},
            fields=[
                "schedule_date",
                "depreciation_amount",
                "accumulated_depreciation_amount",
                "journal_entry",
            ],
            order_by="schedule_date asc",
        )

        return {
            "asset_name": doc.asset_name,
            "asset": doc.name,
            "gross_purchase_amount": doc.gross_purchase_amount,
            "current_value": doc.value_after_depreciation or doc.gross_purchase_amount,
            "depreciation_method": doc.depreciation_method,
            "schedule": schedule,
            "schedule_count": len(schedule),
        }
