import re

import frappe
from erpnext_ai_bots.tools.base import BaseTool

# Disallowed statement keywords — any of these at the start of the query are blocked.
_FORBIDDEN_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|RENAME"
    r"|GRANT|REVOKE|LOCK|UNLOCK|CALL|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def _validate_select_only(query: str) -> None:
    """Raise ValueError if the query is not a plain SELECT statement."""
    stripped = query.strip()
    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError(
            "Only SELECT queries are allowed. "
            f"Your query starts with: {stripped[:40]!r}"
        )
    if _FORBIDDEN_PATTERN.search(stripped):
        raise ValueError(
            "Query contains a forbidden keyword (INSERT/UPDATE/DELETE/DROP/etc.). "
            "Only read-only SELECT statements are permitted."
        )
    # Block sub-statements that could mutate data inside a SELECT context
    if re.search(r"\b(INTO\s+OUTFILE|INTO\s+DUMPFILE)\b", stripped, re.IGNORECASE):
        raise ValueError("SELECT ... INTO OUTFILE/DUMPFILE is not permitted.")


def _execute_with_custom_db(query: str, limit: int) -> list:
    """Run query via a direct pymysql connection using credentials from AI Bot Settings."""
    try:
        import pymysql  # noqa: PLC0415 — optional dependency
    except ImportError as exc:
        raise RuntimeError(
            "pymysql is not installed. Add `pymysql` to requirements.txt and "
            "run `bench pip install pymysql`."
        ) from exc

    settings = frappe.get_cached_doc("AI Bot Settings")
    conn = pymysql.connect(
        host=settings.db_host or "localhost",
        port=int(settings.db_port or 3306),
        user=settings.db_user,
        password=settings.get_password("db_password"),
        database=settings.db_name,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return list(cursor.fetchmany(limit))
    finally:
        conn.close()


def _execute_with_frappe_db(query: str, limit: int) -> list:
    """Run query through the existing Frappe DB connection (no extra credentials needed)."""
    # frappe.db.sql returns a list of dicts when as_dict=True
    rows = frappe.db.sql(query, as_dict=True)
    return rows[:limit]


class RawSQLTool(BaseTool):
    name = "core.raw_sql"
    description = (
        "Execute a read-only SQL SELECT query directly against the ERPNext MariaDB database. "
        "Use this for complex queries that need JOINs, GROUP BY, SUM, COUNT, etc. "
        "ERPNext table names are prefixed with 'tab' — e.g. `tabSales Invoice`, "
        "`tabCustomer`, `tabItem`, `tabPurchase Invoice`, `tabStock Ledger Entry`, "
        "`tabJournal Entry`, `tabEmployee`, `tabSalary Slip`, `tabBin` (stock levels), "
        "`tabTerritory`, `tabWarehouse`, `tabCompany`. "
        "Common fields: name (document ID), creation, modified, owner, docstatus "
        "(0=Draft, 1=Submitted, 2=Cancelled). "
        "ONLY SELECT queries are allowed. Max 100 rows returned."
    )
    parameters = {
        "query": {
            "type": "string",
            "description": (
                "The SQL SELECT query to execute. "
                "Always qualify table names with backticks when they contain spaces "
                "(e.g. `tabSales Invoice`). Always include a LIMIT clause."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Max rows to return (default 100, max 100).",
        },
    }
    required_params = ["query"]
    action_type = "Read"

    def execute(self, query: str, limit: int = 100, **kwargs) -> dict:
        limit = min(int(limit), 100)

        try:
            _validate_select_only(query)
        except ValueError as exc:
            return {"error": str(exc), "rows": []}

        # Decide which execution path to use
        settings = frappe.get_cached_doc("AI Bot Settings")
        use_custom = bool(settings.db_user and settings.db_name)

        try:
            if use_custom:
                try:
                    rows = _execute_with_custom_db(query, limit)
                except Exception:
                    # Custom DB failed — fall back to Frappe's connection
                    rows = _execute_with_frappe_db(query, limit)
            else:
                rows = _execute_with_frappe_db(query, limit)
        except Exception as exc:
            frappe.log_error(
                title="core.raw_sql execution error",
                message=frappe.get_traceback(),
            )
            return {
                "error": f"Query failed: {type(exc).__name__}: {exc}",
                "rows": [],
            }

        return {"rows": rows, "count": len(rows)}
