import frappe
from frappe import _
from frappe.utils import flt
from erpnext_ai_bots.tools.base import BaseTool


class SendReportEmailTool(BaseTool):
    name = "core.send_report_email"
    description = (
        "Send a professional HTML report email with styled tables, KPI metric cards, "
        "and bar charts. Use this when the user asks to email a report, dashboard, "
        "analytics summary, or any data that benefits from visual presentation. "
        "Pass structured data and the tool renders it into a polished email template. "
        "Charts are rendered as CSS-only bars (no images needed). "
        "For simple text emails, use core.send_email instead."
    )
    parameters = {
        "recipients": {
            "type": "string",
            "description": (
                "Comma-separated email addresses. Use 'self' or 'me' to send "
                "to the current user's email address."
            ),
        },
        "subject": {
            "type": "string",
            "description": "Email subject line.",
        },
        "title": {
            "type": "string",
            "description": "Report title shown in the email header.",
        },
        "subtitle": {
            "type": "string",
            "description": "Optional subtitle (e.g. date range, company name).",
        },
        "kpis": {
            "type": "array",
            "description": (
                "List of KPI metric cards to show at the top. Each item: "
                '{"label": "Total Sales", "value": "1,250,000", "change": "+12%", "good": true}. '
                '"change" and "good" are optional. "good" controls color (true=green, false=red).'
            ),
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "change": {"type": "string"},
                    "good": {"type": "boolean"},
                },
            },
        },
        "tables": {
            "type": "array",
            "description": (
                "List of data tables. Each item: "
                '{"title": "Top Customers", "headers": ["Customer", "Revenue", "Orders"], '
                '"rows": [["John", "50,000", "12"], ...], '
                '"highlight_col": 1}. '
                '"highlight_col" (0-indexed) makes that column bold. Optional.'
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "headers": {"type": "array", "items": {"type": "string"}},
                    "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "highlight_col": {"type": "integer"},
                },
            },
        },
        "charts": {
            "type": "array",
            "description": (
                "List of horizontal bar charts. Each item: "
                '{"title": "Sales by Branch", "bars": [{"label": "Branch A", "value": 50000, "display": "50,000"}, ...], '
                '"color": "#6c5ce7"}. '
                '"color" is optional (default purple). "display" is the formatted label shown on the bar.'
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "bars": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "number"},
                                "display": {"type": "string"},
                            },
                        },
                    },
                    "color": {"type": "string"},
                },
            },
        },
        "sections": {
            "type": "array",
            "description": (
                "Optional free-form HTML sections. Each item: "
                '{"title": "Notes", "html": "<p>Some commentary...</p>"}.'
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "html": {"type": "string"},
                },
            },
        },
        "cc": {
            "type": "string",
            "description": "Optional CC recipients (comma-separated emails).",
        },
        "accent_color": {
            "type": "string",
            "description": "Optional accent color hex (default: from AI Bot Settings or #6c5ce7).",
        },
    }
    required_params = ["recipients", "subject", "title"]
    action_type = "Create"
    required_ptype = None

    def execute(self, recipients, subject, title, subtitle=None, kpis=None,
                tables=None, charts=None, sections=None, cc=None,
                accent_color=None, **kwargs):
        # Resolve recipients
        user_email = frappe.session.user
        resolved = []
        for r in recipients.split(","):
            r = r.strip()
            if r.lower() in ("self", "me", "my email", "myself"):
                resolved.append(user_email)
            elif "@" in r:
                resolved.append(r)

        if not resolved:
            return {"error": f"No valid email addresses found in: {recipients}"}

        # Get accent color
        if not accent_color:
            try:
                settings = frappe.get_cached_doc("AI Bot Settings")
                accent_color = settings.accent_color or "#6c5ce7"
            except Exception:
                accent_color = "#6c5ce7"

        # Build the HTML email
        html = self._render_email(
            title=title,
            subtitle=subtitle,
            kpis=kpis or [],
            tables=tables or [],
            charts=charts or [],
            sections=sections or [],
            accent_color=accent_color,
        )

        try:
            frappe.sendmail(
                recipients=resolved,
                cc=cc.split(",") if cc else None,
                subject=subject,
                message=html,
                now=True,
            )
            return {
                "status": "sent",
                "recipients": resolved,
                "subject": subject,
                "message": f"Report email sent to {', '.join(resolved)}",
            }
        except Exception as e:
            return {"error": f"Failed to send email: {str(e)}"}

    def _render_email(self, title, subtitle, kpis, tables, charts, sections,
                      accent_color):
        """Render the full HTML email with inline CSS (email-safe)."""
        parts = []

        # KPI cards
        if kpis:
            parts.append(self._render_kpis(kpis, accent_color))

        # Charts
        for chart in charts:
            parts.append(self._render_chart(chart, accent_color))

        # Tables
        for table in tables:
            parts.append(self._render_table(table, accent_color))

        # Free-form sections
        for section in sections:
            sec_title = _safe(section.get("title", ""))
            sec_html = section.get("html", "")
            parts.append(f"""
                <div style="margin-bottom:24px;">
                    {f'<h3 style="margin:0 0 12px;font-size:16px;color:#1e293b;">{sec_title}</h3>' if sec_title else ''}
                    <div style="font-size:14px;color:#475569;line-height:1.6;">{sec_html}</div>
                </div>
            """)

        body_content = "\n".join(parts)
        subtitle_html = (
            f'<p style="margin:4px 0 0;font-size:13px;opacity:0.85;">{_safe(subtitle)}</p>'
            if subtitle else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:680px;margin:0 auto;background:#ffffff;">
  <!-- Header -->
  <div style="background:{accent_color};padding:28px 32px;color:#ffffff;">
    <h1 style="margin:0;font-size:22px;font-weight:700;">{_safe(title)}</h1>
    {subtitle_html}
  </div>
  <!-- Body -->
  <div style="padding:28px 32px;">
    {body_content}
  </div>
  <!-- Footer -->
  <div style="padding:16px 32px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center;">
    Generated by AI Oracle &middot; {frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd MMM yyyy, hh:mm a")}
  </div>
</div>
</body>
</html>"""

    def _render_kpis(self, kpis, accent_color):
        """Render KPI metric cards as a responsive table row."""
        cells = []
        for kpi in kpis[:6]:
            label = _safe(kpi.get("label", ""))
            value = _safe(str(kpi.get("value", "")))
            change = kpi.get("change", "")
            good = kpi.get("good", True)
            change_color = "#16a34a" if good else "#dc2626"

            change_html = ""
            if change:
                change_html = (
                    f'<div style="font-size:12px;color:{change_color};margin-top:4px;">'
                    f'{_safe(str(change))}</div>'
                )

            cells.append(f"""
                <td style="padding:16px;background:#f8fafc;border-radius:8px;text-align:center;vertical-align:top;">
                    <div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{label}</div>
                    <div style="font-size:24px;font-weight:700;color:#1e293b;">{value}</div>
                    {change_html}
                </td>
            """)

        # Add spacer cells between KPIs
        spaced = []
        for i, cell in enumerate(cells):
            spaced.append(cell)
            if i < len(cells) - 1:
                spaced.append('<td style="width:12px;"></td>')

        return f"""
            <table style="width:100%;border-collapse:separate;border-spacing:0;margin-bottom:24px;" cellpadding="0" cellspacing="0">
                <tr>{" ".join(spaced)}</tr>
            </table>
        """

    def _render_chart(self, chart, accent_color):
        """Render a horizontal bar chart using CSS-only bars."""
        title = _safe(chart.get("title", ""))
        bars = chart.get("bars", [])
        color = chart.get("color", accent_color)

        if not bars:
            return ""

        max_val = max(flt(b.get("value", 0)) for b in bars) or 1
        bar_rows = []

        for bar in bars[:15]:
            label = _safe(bar.get("label", ""))
            value = flt(bar.get("value", 0))
            display = _safe(bar.get("display", str(value)))
            width_pct = max(int(value / max_val * 100), 2)

            bar_rows.append(f"""
                <tr>
                    <td style="padding:4px 12px 4px 0;font-size:13px;color:#475569;white-space:nowrap;width:1%;vertical-align:middle;">{label}</td>
                    <td style="padding:4px 0;vertical-align:middle;">
                        <div style="background:#f1f5f9;border-radius:4px;overflow:hidden;">
                            <div style="background:{color};height:24px;width:{width_pct}%;border-radius:4px;display:flex;align-items:center;padding:0 8px;">
                                <span style="font-size:11px;color:#ffffff;font-weight:600;white-space:nowrap;">{display}</span>
                            </div>
                        </div>
                    </td>
                </tr>
            """)

        return f"""
            <div style="margin-bottom:24px;">
                <h3 style="margin:0 0 12px;font-size:16px;color:#1e293b;">{title}</h3>
                <table style="width:100%;border-collapse:collapse;" cellpadding="0" cellspacing="0">
                    {"".join(bar_rows)}
                </table>
            </div>
        """

    def _render_table(self, table, accent_color):
        """Render a styled data table."""
        title = _safe(table.get("title", ""))
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        highlight_col = table.get("highlight_col")

        if not headers and not rows:
            return ""

        header_cells = []
        for h in headers:
            header_cells.append(
                f'<th style="padding:10px 12px;text-align:left;font-size:11px;'
                f'text-transform:uppercase;letter-spacing:0.05em;color:#64748b;'
                f'border-bottom:2px solid {accent_color};background:#f8fafc;">'
                f'{_safe(str(h))}</th>'
            )

        body_rows = []
        for i, row in enumerate(rows[:50]):
            bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
            cells = []
            for j, cell in enumerate(row):
                weight = "700" if j == highlight_col else "400"
                cells.append(
                    f'<td style="padding:10px 12px;font-size:13px;color:#1e293b;'
                    f'border-bottom:1px solid #e2e8f0;font-weight:{weight};">'
                    f'{_safe(str(cell))}</td>'
                )
            body_rows.append(f'<tr style="background:{bg};">{"".join(cells)}</tr>')

        return f"""
            <div style="margin-bottom:24px;">
                {f'<h3 style="margin:0 0 12px;font-size:16px;color:#1e293b;">{title}</h3>' if title else ''}
                <table style="width:100%;border-collapse:collapse;" cellpadding="0" cellspacing="0">
                    <thead><tr>{"".join(header_cells)}</tr></thead>
                    <tbody>{"".join(body_rows)}</tbody>
                </table>
            </div>
        """


def _safe(text):
    """Escape HTML special characters."""
    return frappe.utils.escape_html(str(text)) if text else ""
