"""OAuth 2.0 PKCE client for community branch.

In the community branch, OAuth PKCE is used for USER AUTHENTICATION
against the customer's own Identity Provider (Keycloak, Auth0, etc.),
NOT for license validation.
"""
import frappe
import hashlib
import base64
import secrets
import requests
from urllib.parse import urlencode


class OAuthPKCEClient:
    """OAuth 2.0 Authorization Code + PKCE for user auth via external IdP."""

    def __init__(self):
        self.settings = frappe.get_cached_doc("AI Bot Settings")
        self.base_url = self.settings.oauth_provider_url
        self.client_id = self.settings.oauth_client_id

    def generate_auth_url(self, redirect_uri: str) -> dict:
        """Generate PKCE challenge and return the authorization URL."""
        if not self.base_url or not self.client_id:
            frappe.throw("OAuth is not configured. Set provider URL and client ID in AI Bot Settings.")

        code_verifier = secrets.token_urlsafe(96)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(32)

        # Store verifier and state in cache (expires in 10 min)
        cache = frappe.cache()
        cache.set_value(f"oauth_pkce_state:{state}", {
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "user": frappe.session.user,
        }, expires_in_sec=600)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = f"{self.base_url}/authorize?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state}

    def exchange_code(self, authorization_code: str, state: str) -> dict:
        """Exchange the authorization code for tokens."""
        cache = frappe.cache()
        stored = cache.get_value(f"oauth_pkce_state:{state}")

        if not stored:
            frappe.throw("OAuth state expired or invalid. Please try again.")

        code_verifier = stored["code_verifier"]
        redirect_uri = stored["redirect_uri"]

        # Clear the state
        cache.delete_value(f"oauth_pkce_state:{state}")

        response = requests.post(
            f"{self.base_url}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "code": authorization_code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=30,
        )

        if response.status_code != 200:
            frappe.throw(f"OAuth token exchange failed: {response.text}")

        tokens = response.json()

        # Store access token
        settings = frappe.get_doc("AI Bot Settings")
        settings.oauth_token = tokens["access_token"]
        settings.oauth_token_expiry = frappe.utils.add_to_date(
            frappe.utils.now_datetime(),
            seconds=tokens.get("expires_in", 3600),
        )
        settings.save(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "authenticated",
            "expires_in": tokens.get("expires_in", 3600),
        }
