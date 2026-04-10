"""OpenAI OAuth PKCE endpoints.

Implements the full OAuth 2.0 PKCE flow for connecting a user's
ChatGPT account (Plus/Pro/Max) to call the Codex API on their behalf.
"""
import frappe
import json
import base64
import hashlib
import secrets
import requests
from frappe import _

# OpenAI Codex CLI public OAuth constants
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
AUTH_URL = "https://auth.openai.com/oauth/authorize"
REDIRECT_URI = "http://localhost:1455/auth/callback"


def _b64url(data: bytes) -> str:
    """Base64url-encode bytes with NO padding (RFC 7636)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_pkce_pair() -> tuple:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    import os
    verifier = _b64url(os.urandom(64))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _b64url(digest)
    return verifier, challenge


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1] + "=="
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


@frappe.whitelist()
def start_oauth():
    """Generate PKCE challenge and return the OpenAI authorization URL.

    The user opens this URL in a new tab, logs into OpenAI, then copies
    the localhost callback URL back into the app.
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please log in first"), frappe.AuthenticationError)

    verifier, challenge = _make_pkce_pair()
    state = _b64url(secrets.token_bytes(32))

    # Store verifier and state in Redis cache (expires in 10 min)
    frappe.cache().set_value(
        f"openai_pkce:{state}",
        {"code_verifier": verifier, "user": user},
        expires_in_sec=600,
    )

    from urllib.parse import quote
    params = "&".join([
        "response_type=code",
        f"client_id={CLIENT_ID}",
        f"redirect_uri={quote(REDIRECT_URI, safe='')}",
        f"scope={quote('openid profile email offline_access', safe='')}",
        f"code_challenge={challenge}",
        "code_challenge_method=S256",
        f"state={state}",
        "codex_cli_simplified_flow=true",
        "originator=codex_cli_rs",
    ])

    return {"auth_url": f"{AUTH_URL}?{params}"}


@frappe.whitelist(methods=["POST"])
def exchange_code(code: str, state: str):
    """Exchange the authorization code for access + refresh tokens."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please log in first"), frappe.AuthenticationError)

    if not code or not state:
        frappe.throw(_("Missing authorization code or state"))

    # Retrieve and validate PKCE state
    cache_key = f"openai_pkce:{state}"
    stored = frappe.cache().get_value(cache_key)
    if not stored:
        frappe.throw(_("OAuth state expired or invalid. Please start the flow again."))

    if stored["user"] != user:
        frappe.throw(_("OAuth state does not belong to this user"), frappe.PermissionError)

    verifier = stored["code_verifier"]
    frappe.cache().delete_value(cache_key)

    # Exchange code for tokens (MUST be form-urlencoded, NOT JSON)
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": verifier,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        frappe.throw(_("Token exchange failed: {0}").format(resp.text))

    token_data = resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token:
        frappe.throw(_("No access token received from OpenAI"))

    # Extract ChatGPT account ID from JWT
    payload = _decode_jwt_payload(access_token)
    account_id = payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id", "")

    # Store tokens in DocType (one record per user)
    _save_tokens(user, access_token, refresh_token, account_id, expires_in)

    return {"success": True, "account_id": account_id}


@frappe.whitelist(methods=["POST"])
def refresh_access_token():
    """Use the stored refresh token to get a new access token."""
    user = frappe.session.user
    token_doc = _get_token_doc(user)
    if not token_doc:
        frappe.throw(_("No OpenAI connection found. Please connect first."))

    refresh_tok = token_doc.get_password("refresh_token")
    if not refresh_tok:
        frappe.throw(_("No refresh token stored. Please reconnect."))

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": CLIENT_ID,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        # Mark as expired
        frappe.db.set_value("AI OpenAI Token", user, "status", "Expired")
        frappe.db.commit()
        frappe.throw(_("Token refresh failed. Please reconnect."))

    token_data = resp.json()
    new_access = token_data.get("access_token", "")
    new_refresh = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    account_id = token_doc.chatgpt_account_id
    if new_access:
        payload = _decode_jwt_payload(new_access)
        account_id = payload.get("https://api.openai.com/auth", {}).get(
            "chatgpt_account_id", account_id
        )

    _save_tokens(
        user,
        new_access,
        new_refresh or refresh_tok,
        account_id,
        expires_in,
    )

    return {"success": True}


@frappe.whitelist(methods=["POST"])
def disconnect():
    """Remove stored OpenAI tokens for the current user."""
    user = frappe.session.user
    if frappe.db.exists("AI OpenAI Token", user):
        frappe.delete_doc("AI OpenAI Token", user, ignore_permissions=True)
        frappe.db.commit()
    return {"success": True, "message": "Disconnected"}


@frappe.whitelist()
def oauth_status():
    """Check if the current user has an active OpenAI connection.

    Also checks for a BYOK API key — if one is set, the user is effectively
    connected even without OAuth tokens.
    """
    # Check BYOK API key first (may not be set — that's fine)
    try:
        settings = frappe.get_cached_doc("AI Bot Settings")
        api_key = settings.get_password("api_key") if settings.api_key else None
        if api_key:
            return {
                "connected": True,
                "status": "Connected",
                "account_id": "API Key (BYOK)",
                "connected_at": None,
                "token_expiry": None,
            }
    except Exception:
        pass

    # Fall back to OAuth token check
    user = frappe.session.user
    token_doc = _get_token_doc(user)
    if not token_doc:
        return {"connected": False}

    return {
        "connected": token_doc.status == "Connected",
        "status": token_doc.status,
        "account_id": token_doc.chatgpt_account_id,
        "connected_at": str(token_doc.connected_at) if token_doc.connected_at else None,
        "token_expiry": str(token_doc.token_expiry) if token_doc.token_expiry else None,
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _get_token_doc(user: str):
    """Get the AI OpenAI Token doc for a user, or None."""
    if frappe.db.exists("AI OpenAI Token", user):
        return frappe.get_doc("AI OpenAI Token", user)
    return None


def _save_tokens(user, access_token, refresh_token, account_id, expires_in):
    """Create or update the token record for a user."""
    expiry = frappe.utils.add_to_date(
        frappe.utils.now_datetime(), seconds=expires_in
    )

    if frappe.db.exists("AI OpenAI Token", user):
        doc = frappe.get_doc("AI OpenAI Token", user)
        doc.access_token = access_token
        doc.refresh_token = refresh_token
        doc.chatgpt_account_id = account_id
        doc.token_expiry = expiry
        doc.status = "Connected"
        doc.connected_at = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "AI OpenAI Token",
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "chatgpt_account_id": account_id,
            "token_expiry": expiry,
            "status": "Connected",
            "connected_at": frappe.utils.now_datetime(),
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
