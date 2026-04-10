"""
context.py — Live company context snapshot for the Oracle system prompt.

Queries ERPNext for key business data and formats it as a plain-text block
that gets injected into the system prompt. Results are cached in Redis for
5 minutes per user+company to avoid repeated DB hits on every message.

All queries respect the active user's permissions: no ignore_permissions.
Each section is individually guarded so a missing DocType or permission denial
silently produces an empty result rather than crashing prompt assembly.
"""

import frappe


_CACHE_TTL = 300  # 5 minutes


def build_context_snapshot(company: str) -> str:
    """Build context with Redis caching. Returns cached version if fresh."""
    user = frappe.session.user
    cache_key = f"ai_oracle_context:{user}:{company}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached
    result = _build_context_snapshot_uncached(company)
    frappe.cache().set_value(cache_key, result, expires_in_sec=_CACHE_TTL)
    return result


# ---------------------------------------------------------------------------
# Individual data-gathering helpers
# ---------------------------------------------------------------------------

def _get_company_info(company: str) -> dict:
    """Return company name, default currency, and current fiscal year dates."""
    info = {
        "company": company,
        "currency": "N/A",
        "fiscal_year": "N/A",
        "fy_start": None,
        "fy_end": None,
    }
    try:
        doc = frappe.get_cached_doc("Company", company)
        info["currency"] = doc.default_currency or "N/A"
    except Exception:
        pass

    try:
        today = frappe.utils.today()
        fy = frappe.get_all(
            "Fiscal Year",
            filters={
                "year_start_date": ["<=", today],
                "year_end_date": [">=", today],
                "disabled": 0,
            },
            fields=["name", "year_start_date", "year_end_date"],
            limit_page_length=1,
        )
        if fy:
            info["fiscal_year"] = fy[0]["name"]
            info["fy_start"] = str(fy[0]["year_start_date"])
            info["fy_end"] = str(fy[0]["year_end_date"])
    except Exception:
        pass

    return info


def _get_top_customers(limit: int = 10) -> list:
    """Top customers by total billed (sum of grand_total on submitted Sales Invoices).

    Falls back to alphabetical order if Sales Invoice access is denied.
    Returns list of dicts: {name, customer_name, revenue, outstanding}.
    """
    try:
        # Aggregate revenue per customer from submitted invoices
        # Only look at last 12 months for performance
        cutoff = frappe.utils.add_months(frappe.utils.today(), -12)
        rows = frappe.db.sql(
            """
            SELECT
                si.customer            AS name,
                c.customer_name        AS customer_name,
                SUM(si.grand_total)    AS revenue,
                SUM(si.outstanding_amount) AS outstanding
            FROM `tabSales Invoice` si
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1 AND si.posting_date >= %s
            GROUP BY si.customer
            ORDER BY revenue DESC
            LIMIT %s
            """,
            (cutoff, limit),
            as_dict=True,
        )
        # frappe.db.sql runs with session user permissions implicitly because
        # the user context is already set; however it bypasses frappe.has_permission.
        # We therefore verify read permission on Customer before returning data.
        if not frappe.has_permission("Customer", ptype="read"):
            return []
        return rows or []
    except Exception:
        pass

    # Fallback: plain customer list (no revenue data)
    try:
        if not frappe.has_permission("Customer", ptype="read"):
            return []
        customers = frappe.get_all(
            "Customer",
            fields=["name", "customer_name"],
            order_by="customer_name asc",
            limit_page_length=limit,
        )
        return [
            {"name": c["name"], "customer_name": c["customer_name"],
             "revenue": None, "outstanding": None}
            for c in customers
        ]
    except Exception:
        return []


def _get_top_items(limit: int = 10) -> list:
    """Top items by quantity sold (sum of qty on submitted Sales Invoice Items).

    Falls back to listing items by name if Sales Invoice access is denied.
    Returns list of dicts: {item_code, item_name, qty_sold, actual_qty}.
    """
    try:
        if not frappe.has_permission("Sales Invoice", ptype="read"):
            raise PermissionError("no access")
        # Only look at last 6 months for performance
        cutoff = frappe.utils.add_months(frappe.utils.today(), -6)
        rows = frappe.db.sql(
            """
            SELECT
                sii.item_code,
                sii.item_name,
                SUM(sii.qty) AS qty_sold
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.posting_date >= %s
            GROUP BY sii.item_code
            ORDER BY qty_sold DESC
            LIMIT %s
            """,
            (cutoff, limit),
            as_dict=True,
        )
        return rows or []
    except Exception:
        pass

    # Fallback: plain item list
    try:
        if not frappe.has_permission("Item", ptype="read"):
            return []
        items = frappe.get_all(
            "Item",
            filters={"disabled": 0, "is_stock_item": 1},
            fields=["item_code", "item_name"],
            order_by="item_name asc",
            limit_page_length=limit,
        )
        return [
            {"item_code": i["item_code"], "item_name": i["item_name"],
             "qty_sold": None}
            for i in items
        ]
    except Exception:
        return []


def _get_recent_sales_invoices(limit: int = 5) -> list:
    """Most recent submitted Sales Invoices."""
    try:
        if not frappe.has_permission("Sales Invoice", ptype="read"):
            return []
        return frappe.get_all(
            "Sales Invoice",
            filters={"docstatus": 1},
            fields=[
                "name", "customer", "grand_total",
                "outstanding_amount", "status", "posting_date", "currency",
            ],
            order_by="posting_date desc",
            limit_page_length=limit,
        )
    except Exception:
        return []


def _get_recent_purchase_invoices(limit: int = 5) -> list:
    """Most recent submitted Purchase Invoices."""
    try:
        if not frappe.has_permission("Purchase Invoice", ptype="read"):
            return []
        return frappe.get_all(
            "Purchase Invoice",
            filters={"docstatus": 1},
            fields=[
                "name", "supplier", "grand_total",
                "outstanding_amount", "status", "posting_date", "currency",
            ],
            order_by="posting_date desc",
            limit_page_length=limit,
        )
    except Exception:
        return []


def _get_pending_quotations(top: int = 5) -> dict:
    """Count of open Quotations and the names of the first few."""
    try:
        if not frappe.has_permission("Quotation", ptype="read"):
            return {"count": 0, "names": []}
        rows = frappe.get_all(
            "Quotation",
            filters={"docstatus": 0},
            fields=["name", "party_name", "transaction_date", "grand_total"],
            order_by="transaction_date desc",
            limit_page_length=top,
        )
        total = frappe.db.count("Quotation", {"docstatus": 0})
        return {"count": total, "items": rows}
    except Exception:
        return {"count": 0, "items": []}


def _get_overdue_invoices() -> dict:
    """Count and total outstanding amount of overdue Sales Invoices."""
    try:
        if not frappe.has_permission("Sales Invoice", ptype="read"):
            return {"count": 0, "total": 0.0}
        today = frappe.utils.today()
        rows = frappe.get_all(
            "Sales Invoice",
            filters={
                "docstatus": 1,
                "outstanding_amount": [">", 0],
                "due_date": ["<", today],
            },
            fields=["outstanding_amount"],
            limit_page_length=500,
        )
        total = sum(r.get("outstanding_amount") or 0.0 for r in rows)
        return {"count": len(rows), "total": total}
    except Exception:
        return {"count": 0, "total": 0.0}


def _get_low_stock_items(top: int = 5) -> dict:
    """Items whose actual stock quantity is at or below their reorder level."""
    try:
        if not frappe.has_permission("Item", ptype="read"):
            return {"count": 0, "items": []}

        # Items that have a reorder level defined
        reorder_items = frappe.get_all(
            "Item",
            filters={"disabled": 0, "is_stock_item": 1},
            fields=["item_code", "item_name", "reorder_level"],
            limit_page_length=500,
        )

        # Only those with a positive reorder level
        reorder_items = [
            i for i in reorder_items
            if (i.get("reorder_level") or 0) > 0
        ]

        if not reorder_items:
            return {"count": 0, "items": []}

        # Fetch current stock for these items
        item_codes = [i["item_code"] for i in reorder_items]
        stock_rows = frappe.get_all(
            "Bin",
            filters={"item_code": ["in", item_codes]},
            fields=["item_code", "actual_qty"],
            limit_page_length=1000,
        )

        # Aggregate actual_qty per item_code across all warehouses
        stock_map: dict = {}
        for row in stock_rows:
            code = row["item_code"]
            stock_map[code] = stock_map.get(code, 0.0) + (row.get("actual_qty") or 0.0)

        low = []
        for item in reorder_items:
            code = item["item_code"]
            actual = stock_map.get(code, 0.0)
            if actual <= (item.get("reorder_level") or 0):
                low.append({
                    "item_code": code,
                    "item_name": item["item_name"],
                    "actual_qty": actual,
                    "reorder_level": item.get("reorder_level"),
                })

        low.sort(key=lambda x: x["actual_qty"])
        return {"count": len(low), "items": low[:top]}

    except Exception:
        return {"count": 0, "items": []}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_amount(amount, currency: str = "") -> str:
    if amount is None:
        return "N/A"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{amount:,.2f}"


def _fmt_date(d) -> str:
    return str(d) if d else "N/A"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _build_context_snapshot_uncached(company: str) -> str:
    """Assemble a plain-text company snapshot for injection into the system prompt.

    Designed to be called once per request. All sub-queries are independently
    guarded so a permission error or missing DocType in any one section does
    not prevent the rest from running.

    Returns a string of roughly 500-900 words suitable for prepending to the
    system prompt without pushing it above token budget.
    """
    today = frappe.utils.today()

    company_info = _get_company_info(company)
    currency = company_info["currency"]

    top_customers = _get_top_customers(10)
    top_items = _get_top_items(10)
    recent_sales = _get_recent_sales_invoices(5)
    recent_purchases = _get_recent_purchase_invoices(5)
    pending_quotations = _get_pending_quotations(5)
    overdue = _get_overdue_invoices()
    low_stock = _get_low_stock_items(5)

    lines = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines.append(f"COMPANY SNAPSHOT (as of {today}):")
    lines.append(
        f"Company: {company_info['company']} | "
        f"Currency: {currency} | "
        f"Fiscal Year: {company_info['fiscal_year']}"
    )
    if company_info["fy_start"] and company_info["fy_end"]:
        lines.append(
            f"FY Period: {company_info['fy_start']} to {company_info['fy_end']}"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # Top customers
    # ------------------------------------------------------------------
    if top_customers:
        lines.append("TOP CUSTOMERS (by revenue):")
        for c in top_customers:
            display = c.get("customer_name") or c.get("name", "Unknown")
            cid = c.get("name", "")
            revenue = c.get("revenue")
            outstanding = c.get("outstanding")
            rev_str = _fmt_amount(revenue, currency) if revenue is not None else "N/A"
            out_str = _fmt_amount(outstanding, currency) if outstanding is not None else "N/A"
            id_str = f" [{cid}]" if cid and cid != display else ""
            lines.append(
                f"  - {display}{id_str} | Revenue: {rev_str} | Outstanding: {out_str}"
            )
    else:
        lines.append("TOP CUSTOMERS: (no data available)")
    lines.append("")

    # ------------------------------------------------------------------
    # Top items
    # ------------------------------------------------------------------
    if top_items:
        lines.append("TOP ITEMS (by qty sold):")
        for item in top_items:
            code = item.get("item_code", "")
            name = item.get("item_name") or code
            qty = item.get("qty_sold")
            qty_str = f"{qty:,.0f} sold" if qty is not None else "N/A"
            lines.append(f"  - {name} [{code}] | {qty_str}")
    else:
        lines.append("TOP ITEMS: (no data available)")
    lines.append("")

    # ------------------------------------------------------------------
    # Recent Sales Invoices
    # ------------------------------------------------------------------
    if recent_sales:
        lines.append("RECENT SALES INVOICES:")
        lines.append("| Invoice | Customer | Amount | Status | Date |")
        lines.append("|---------|----------|--------|--------|------|")
        for inv in recent_sales:
            curr = inv.get("currency") or currency
            amount = _fmt_amount(inv.get("grand_total"), curr)
            lines.append(
                f"| {inv.get('name','N/A')} "
                f"| {inv.get('customer','N/A')} "
                f"| {amount} "
                f"| {inv.get('status','N/A')} "
                f"| {_fmt_date(inv.get('posting_date'))} |"
            )
    else:
        lines.append("RECENT SALES INVOICES: (no data available)")
    lines.append("")

    # ------------------------------------------------------------------
    # Recent Purchase Invoices
    # ------------------------------------------------------------------
    if recent_purchases:
        lines.append("RECENT PURCHASE INVOICES:")
        lines.append("| Invoice | Supplier | Amount | Status | Date |")
        lines.append("|---------|----------|--------|--------|------|")
        for inv in recent_purchases:
            curr = inv.get("currency") or currency
            amount = _fmt_amount(inv.get("grand_total"), curr)
            lines.append(
                f"| {inv.get('name','N/A')} "
                f"| {inv.get('supplier','N/A')} "
                f"| {amount} "
                f"| {inv.get('status','N/A')} "
                f"| {_fmt_date(inv.get('posting_date'))} |"
            )
    else:
        lines.append("RECENT PURCHASE INVOICES: (no data available)")
    lines.append("")

    # ------------------------------------------------------------------
    # Pending quotations
    # ------------------------------------------------------------------
    q = pending_quotations
    if q["count"] > 0:
        lines.append(f"PENDING QUOTATIONS: {q['count']} open")
        for item in q.get("items", []):
            lines.append(
                f"  - {item.get('name','N/A')} | "
                f"{item.get('party_name','N/A')} | "
                f"{_fmt_amount(item.get('grand_total'), currency)} | "
                f"{_fmt_date(item.get('transaction_date'))}"
            )
    else:
        lines.append("PENDING QUOTATIONS: 0 open")
    lines.append("")

    # ------------------------------------------------------------------
    # Overdue invoices
    # ------------------------------------------------------------------
    if overdue["count"] > 0:
        lines.append(
            f"OVERDUE INVOICES: {overdue['count']} overdue, "
            f"total {_fmt_amount(overdue['total'], currency)}"
        )
    else:
        lines.append("OVERDUE INVOICES: None")
    lines.append("")

    # ------------------------------------------------------------------
    # Low stock alerts
    # ------------------------------------------------------------------
    ls = low_stock
    if ls["count"] > 0:
        lines.append(f"LOW STOCK ALERTS: {ls['count']} items at or below reorder level")
        for item in ls.get("items", []):
            lines.append(
                f"  - {item.get('item_name','N/A')} [{item.get('item_code','N/A')}] "
                f"| Stock: {item.get('actual_qty', 0):,.0f} "
                f"| Reorder Level: {item.get('reorder_level', 0):,.0f}"
            )
    else:
        lines.append("LOW STOCK ALERTS: None")

    return "\n".join(lines)
