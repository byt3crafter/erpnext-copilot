"""Vision tool — analyze images using a vision-capable AI model.

Uses the ChatGPT OAuth token to call the OpenAI Responses API with
image content. Falls back to describing what we know about the file
if vision is unavailable.
"""
import frappe
import json
import base64
import requests
from frappe import _
from erpnext_ai_bots.tools.base import BaseTool


class AnalyzeImageTool(BaseTool):
    name = "core.analyze_image"
    description = (
        "Analyze an image file using AI vision. Pass the file URL (from an uploaded "
        "attachment) and an optional prompt describing what to look for. "
        "Use this when a user uploads an image and asks 'what is this?' or "
        "'analyze this image'. Supports PNG, JPG, JPEG, GIF, WEBP."
    )
    parameters = {
        "image_url": {
            "type": "string",
            "description": "The URL of the image file (from file upload). Can be relative (/private/files/...) or absolute.",
        },
        "prompt": {
            "type": "string",
            "description": "What to analyze or look for in the image. Default: 'Describe this image in detail.'",
        },
    }
    required_params = ["image_url"]
    action_type = "Read"
    required_ptype = None

    def execute(self, image_url, prompt=None, **kwargs):
        if not prompt:
            prompt = "Describe this image in detail. If it contains a document, invoice, or receipt, extract the key information."

        # Try to get the image as base64
        image_base64 = self._get_image_base64(image_url)
        if not image_base64:
            return {
                "error": f"Could not read image at {image_url}",
                "suggestion": "Make sure the file was uploaded successfully.",
            }

        # Call vision API
        try:
            result = self._call_vision_api(image_base64, prompt)
            return {"analysis": result}
        except Exception as e:
            frappe.log_error(title="Vision analysis failed", message=frappe.get_traceback())
            return {
                "error": f"Vision analysis failed: {str(e)}",
                "suggestion": "The vision model may not be available. Try describing the image to me instead.",
            }

    def _get_image_base64(self, image_url):
        """Read the image file and return base64-encoded data."""
        import os

        try:
            # Try to find the file via Frappe's File doctype first
            file_doc = frappe.get_all(
                "File",
                filters={"file_url": image_url},
                fields=["name", "file_url", "is_private"],
                limit_page_length=1,
            )
            if file_doc:
                # Use Frappe's get_content to read the file properly
                doc = frappe.get_doc("File", file_doc[0]["name"])
                content = doc.get_content()
                if content:
                    if isinstance(content, str):
                        content = content.encode("latin-1")
                    return base64.b64encode(content).decode("ascii")

            # Fallback: try reading from disk directly
            if image_url.startswith("/"):
                # Extract filename
                filename = image_url.split("/files/")[-1] if "/files/" in image_url else ""
                if filename:
                    # Try private files
                    path = frappe.utils.get_site_path("private", "files", filename)
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            return base64.b64encode(f.read()).decode("ascii")
                    # Try public files
                    path = frappe.utils.get_site_path("public", "files", filename)
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            return base64.b64encode(f.read()).decode("ascii")

            # Absolute URL — download it
            if image_url.startswith("http"):
                resp = requests.get(image_url, timeout=15)
                if resp.status_code == 200:
                    return base64.b64encode(resp.content).decode("ascii")
        except Exception as e:
            frappe.log_error(title="Image read failed", message=f"{image_url}: {e}")
        return None

    def _call_vision_api(self, image_base64, prompt):
        """Call the OpenAI API with vision support."""
        # Find the global OAuth token
        tokens = frappe.get_all(
            "AI OpenAI Token",
            filters={"status": "Connected"},
            fields=["name"],
            limit_page_length=1,
            order_by="modified desc",
        )
        if not tokens:
            raise Exception("No OpenAI connection found")

        token_doc = frappe.get_doc("AI OpenAI Token", tokens[0]["name"])
        access_token = token_doc.get_password("access_token")
        account_id = token_doc.chatgpt_account_id

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if account_id:
            headers["chatgpt-account-id"] = account_id

        # Use the ChatGPT Responses API (NOT Codex) with a vision-capable model
        # Codex models don't support images — we use gpt-5.2 which does
        payload = {
            "model": "gpt-5.2",
            "instructions": "You are a helpful assistant that can analyze images in detail.",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{image_base64}",
                        },
                    ],
                }
            ],
            "stream": True,
            "store": False,
        }

        resp = requests.post(
            "https://chatgpt.com/backend-api/codex/responses",
            headers=headers,
            json=payload,
            stream=True,
            timeout=60,
        )

        if resp.status_code != 200:
            raise Exception(f"Vision API returned {resp.status_code}: {resp.text[:200]}")

        # Parse SSE stream for text (handle both bytes and str)
        full_text = ""
        for line_bytes in resp.iter_lines():
            if not line_bytes:
                continue
            line = line_bytes.decode("utf-8") if isinstance(line_bytes, bytes) else line_bytes
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                if chunk.get("type") == "response.output_text.delta":
                    full_text += chunk.get("delta", "")
            except json.JSONDecodeError:
                continue

        return full_text or "No analysis returned"
