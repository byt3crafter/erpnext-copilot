import frappe
from frappe import _
from erpnext_ai_bots.tools.base import BaseTool


class SendEmailTool(BaseTool):
    name = "core.send_email"
    description = (
        "Send an email to any email address. Use this to email reports, "
        "summaries, or data to the user or anyone else. "
        "The email is sent from the system's default outgoing email. "
        "Can include HTML formatting in the body. "
        "Use this when the user says 'email me', 'send me', or 'send to my email'."
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
            "description": "Email subject line",
        },
        "body": {
            "type": "string",
            "description": (
                "Email body content. Can include HTML for formatting. "
                "Use <table>, <b>, <p> tags for rich formatting."
            ),
        },
        "cc": {
            "type": "string",
            "description": "Optional CC recipients (comma-separated emails)",
        },
    }
    required_params = ["recipients", "subject", "body"]
    action_type = "Create"
    required_ptype = None  # No DocType permission needed

    def execute(self, recipients, subject, body, cc=None, **kwargs):
        # Resolve 'self' / 'me' to current user's email
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

        try:
            frappe.sendmail(
                recipients=resolved,
                cc=cc.split(",") if cc else None,
                subject=subject,
                message=body,
                now=True,
            )
            return {
                "status": "sent",
                "recipients": resolved,
                "subject": subject,
                "message": f"Email sent to {', '.join(resolved)}",
            }
        except Exception as e:
            return {"error": f"Failed to send email: {str(e)}"}
