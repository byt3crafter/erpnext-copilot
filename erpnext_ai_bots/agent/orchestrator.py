import frappe
import json
import time
from erpnext_ai_bots.tools.registry import ToolRegistry
from erpnext_ai_bots.agent.streaming import StreamBridge
from erpnext_ai_bots.agent.subagent import SubagentSpawner
from erpnext_ai_bots.agent.prompts import get_system_prompt
from erpnext_ai_bots.guards.permissions import PermissionGuard
from erpnext_ai_bots.tools.sanitizer import InputSanitizer
from erpnext_ai_bots.utils.token_counter import TokenTracker
from erpnext_ai_bots.utils.prompt_defense import check_prompt_injection


class Orchestrator:
    """Single agent that handles all user requests.
    Owns all tools. Streams responses. Spawns subagents only when needed.
    Supports both Anthropic and OpenAI (ChatGPT OAuth) providers.
    """

    def __init__(self, user: str, session_id: str, company: str = None):
        self.user = user
        self.session_id = session_id
        self.company = company or frappe.defaults.get_user_default("company", user)
        self.settings = frappe.get_cached_doc("AI Bot Settings")
        self.provider = self.settings.provider or "Anthropic"

        # Initialize components
        self.tool_registry = ToolRegistry(user=self.user, company=self.company)
        self.permission_guard = PermissionGuard(user=self.user)
        self.sanitizer = InputSanitizer()
        self.token_tracker = TokenTracker(session_id=self.session_id)
        self.stream_bridge = StreamBridge(session_id=self.session_id, user=self.user)

        # Conversation state
        self.messages = self._load_messages()
        self.turn_tool_calls = 0

    def _load_messages(self) -> list:
        session = frappe.get_doc("AI Chat Session", self.session_id)
        if session.messages_json:
            return json.loads(session.messages_json)
        return []

    def _save_messages(self):
        frappe.db.set_value(
            "AI Chat Session",
            self.session_id,
            {
                "messages_json": json.dumps(self.messages, default=str),
                "message_count": len([m for m in self.messages if m["role"] == "user"
                                      and not isinstance(m.get("content"), list)]),
                "last_message_at": frappe.utils.now_datetime(),
                "total_input_tokens": self.token_tracker.total_input,
                "total_output_tokens": self.token_tracker.total_output,
                "total_cost_usd": self.token_tracker.total_cost,
                "total_tool_calls": self.turn_tool_calls,
            },
            update_modified=False,
        )
        frappe.db.commit()

    def handle_message(self, user_message: str, image_url: str = None):
        """Main entry point. Called from the API endpoint."""
        # 1. Prompt injection defense
        check_prompt_injection(user_message)

        # 2. If an image is attached, include the URL in the text so the AI
        #    knows to call core_analyze_image. We don't send the image inline
        #    because private files can't be downloaded by the external API.
        if image_url:
            user_message = f"[Image attached at: {image_url}] {user_message}\n\nUse the core_analyze_image tool with image_url=\"{image_url}\" to analyze this image."
        msg_content = user_message

        self.messages.append({
            "role": "user",
            "content": msg_content,
            "timestamp": frappe.utils.now_datetime().isoformat(),
        })

        # 3. Route to the right provider
        if self.provider == "OpenAI (ChatGPT OAuth)":
            self._openai_loop()
        else:
            self._anthropic_loop()

        # 4. Persist
        self._save_messages()

    # ── OpenAI (ChatGPT OAuth) path ──────────────────────────────────

    def _openai_loop(self):
        """Agent loop using the ChatGPT Codex Responses API.

        Mirrors the Anthropic loop:
          1. Send messages + tool schemas to CodexClient.
          2. Stream text deltas to the frontend via stream_bridge.
          3. If the response contains function calls, execute each one with
             the same permission guard, sanitizer, and audit log used by the
             Anthropic path.
          4. Append tool results to the input and loop.
          5. Repeat until the model stops calling tools or max iterations hit.
        """
        from erpnext_ai_bots.licensing.openai_codex import CodexClient

        client = CodexClient(user=self.user)
        system_prompt = get_system_prompt(self.user, self.company)

        # Resolve model: only accept codex / gpt-5 slugs from settings.
        configured_model = self.settings.model_name or ""
        model = (
            configured_model
            if ("codex" in configured_model or configured_model.startswith("gpt-5"))
            else None
        )
        # model=None lets CodexClient fall back to DEFAULT_CODEX_MODEL.

        tool_schemas = self.tool_registry.get_openai_schemas()
        max_iterations = self.settings.max_tool_calls_per_turn or 15

        # The Codex Responses API keeps a flat input list across turns.
        # We seed it from conversation history on the first call, then
        # append tool-call items and tool-result items each iteration.
        api_input = self._build_openai_messages()

        try:
            for _ in range(max_iterations):
                result = client.send_streaming(
                    messages=api_input,
                    model=model,
                    instructions=system_prompt,
                    tools=tool_schemas,
                    on_delta=lambda delta: self.stream_bridge._publish(
                        "ai_chunk",
                        {"session_id": self.session_id, "text": delta},
                    ),
                )

                # Track token usage for this turn
                usage = result.get("usage", {})
                self.token_tracker.record(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    model=model or "gpt-5.1-codex-mini",
                )

                function_calls = result.get("function_calls", [])
                output_items = result.get("output_items", [])
                response_text = result.get("text", "")

                # No function calls — final assistant turn
                if not function_calls:
                    self.messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": response_text}],
                        "timestamp": frappe.utils.now_datetime().isoformat(),
                        "usage": usage,
                    })
                    self.stream_bridge.send_done()
                    return

                # There are function calls — execute them and loop.
                # Persist a record of this assistant turn (tool-use turn).
                self.messages.append({
                    "role": "assistant",
                    "content": self._serialize_openai_output_items(
                        output_items, response_text
                    ),
                    "timestamp": frappe.utils.now_datetime().isoformat(),
                    "usage": usage,
                })

                # Extend the flat api_input with the assistant's output items
                # (which include the function_call items the model emitted).
                api_input.extend(
                    self._openai_output_items_for_input(output_items)
                )

                # Execute each tool call and collect results
                tool_result_items = self._process_openai_tool_calls(function_calls)

                # Append tool results to api_input for the next request
                api_input.extend(tool_result_items)

                # Persist tool results in conversation history
                self.messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "function_call_output",
                            "call_id": item["call_id"],
                            "output": item["output"],
                        }
                        for item in tool_result_items
                    ],
                    "timestamp": frappe.utils.now_datetime().isoformat(),
                })

            # Exhausted iterations without a final text response
            self.stream_bridge.send_error(
                "Maximum tool call limit reached. Please simplify your request."
            )

        except Exception as e:
            raw_error = str(e)
            # Log the technical error for debugging
            frappe.log_error(title="AI Oracle Error", message=frappe.get_traceback())
            # Show a user-friendly message
            friendly_msg = "I ran into an issue processing your request. Please try again."
            if "permission" in raw_error.lower():
                friendly_msg = "You don't have permission for that action. Ask your admin for access."
            elif "not found" in raw_error.lower():
                friendly_msg = "I couldn't find what you're looking for. Could you double-check the name?"
            elif "timeout" in raw_error.lower():
                friendly_msg = "The request took too long. Please try again with a simpler question."
            self.stream_bridge.send_error(friendly_msg)
            self.messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": friendly_msg}],
                "timestamp": frappe.utils.now_datetime().isoformat(),
            })

    def _build_openai_messages(self) -> list:
        """Build the initial flat input list for the Codex Responses API
        from the stored conversation history (last 20 turns).

        Only plain user/assistant text messages are included. Tool call
        history (function_call and function_call_output items) from prior
        requests are EXCLUDED because the Codex Responses API treats each
        request independently — it doesn't remember previous function calls,
        so sending orphaned tool results causes "No tool call found" errors.
        """
        api_messages = []
        for msg in self.messages[-20:]:
            role = msg["role"]
            content = msg.get("content", "")

            # Handle legacy dict content (e.g. old vision messages)
            if isinstance(content, dict):
                content = content.get("text", str(content))

            if isinstance(content, list):
                # Skip turns that contain function_call_output items
                # (tool results from previous loop iterations).
                has_tool_content = any(
                    isinstance(b, dict) and b.get("type") in (
                        "function_call_output", "function_call"
                    )
                    for b in content
                )
                if has_tool_content:
                    continue

                # Extract plain text parts
                text_parts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = "\n".join(filter(None, text_parts))

            if content:
                api_messages.append({"role": role, "content": content})

        return api_messages

    def _serialize_openai_output_items(
        self, output_items: list, response_text: str
    ) -> list:
        """Convert raw Codex output items into JSON-serialisable content blocks
        for storage in ``self.messages``.

        Text output is stored as ``{"type": "text", "text": "..."}`` and
        function-call items are stored verbatim (they are already plain dicts).
        """
        blocks = []
        if response_text:
            blocks.append({"type": "text", "text": response_text})
        for item in output_items:
            if isinstance(item, dict) and item.get("type") == "function_call":
                blocks.append(item)
        return blocks

    def _openai_output_items_for_input(self, output_items: list) -> list:
        """Return function_call items formatted for the Codex API input.

        The API requires these exact fields when echoing function calls back:
        type, id, call_id, name, arguments. Extra fields cause errors.
        """
        items = []
        for item in output_items:
            if isinstance(item, dict) and item.get("type") == "function_call":
                items.append({
                    "type": "function_call",
                    "id": item.get("id", ""),
                    "call_id": item.get("call_id", ""),
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                })
        return items

    def _process_openai_tool_calls(self, function_calls: list) -> list:
        """Execute OpenAI function calls with permission checks, sanitization,
        and audit logging — the same guards as the Anthropic path.

        Args:
            function_calls: List of dicts produced by ``_consume_stream``::

                [{"id": "fc_...", "call_id": "call_...",
                  "name": "tool_name", "arguments": "{...}"}]

        Returns:
            List of ``function_call_output`` dicts ready to be appended to
            the Codex API input array::

                [{"type": "function_call_output",
                  "call_id": "call_...",
                  "output": "{\"result\": ...}"}]
        """
        result_items = []

        for fc in function_calls:
            # Clear any accumulated messages from the previous tool call so
            # permission popups and msgprint output don't leak to the client.
            if hasattr(frappe.local, "message_log"):
                frappe.local.message_log = []

            self.turn_tool_calls += 1
            openai_name = fc["name"]
            # Convert OpenAI-safe name (underscores) back to dotted name
            # e.g. core_get_list -> core.get_list
            tool_name = openai_name.replace("_", ".", 1)
            call_id = fc["call_id"]
            start_time = time.time()

            # Parse arguments — the model returns a JSON string
            try:
                tool_input = json.loads(fc.get("arguments", "{}") or "{}")
            except (json.JSONDecodeError, ValueError):
                tool_input = {}

            self.stream_bridge.send_tool_start(tool_name, tool_input)

            try:
                # Permission check (same guard as Anthropic path)
                self.permission_guard.check(tool_name, tool_input)

                # Input sanitization
                sanitized_input, blocked_fields = self.sanitizer.sanitize(
                    tool_name, tool_input
                )

                # Subagent spawn
                if tool_name == "meta.spawn_subagent":
                    result = self._handle_subagent(sanitized_input)
                else:
                    tool_fn = self.tool_registry.get_tool(tool_name)
                    result = tool_fn.execute(**sanitized_input)

                exec_time = int((time.time() - start_time) * 1000)

                self._audit_log(
                    tool_name=tool_name,
                    tool_input=sanitized_input,
                    tool_output=result,
                    status="Success",
                    exec_time=exec_time,
                    blocked_fields=blocked_fields,
                )

                self.stream_bridge.send_tool_result(tool_name, result)

                result_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str),
                })

            except frappe.PermissionError as e:
                exec_time = int((time.time() - start_time) * 1000)
                self._audit_log(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output={"error": str(e)},
                    status="PermissionDenied",
                    exec_time=exec_time,
                )
                result_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": f"Permission denied: {e}"}, default=str
                    ),
                })

            except Exception as e:
                exec_time = int((time.time() - start_time) * 1000)
                self._audit_log(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output={"error": str(e)},
                    status="Error",
                    exec_time=exec_time,
                )
                result_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"error": str(e)}, default=str),
                })

        return result_items

    # ── Anthropic path ───────────────────────────────────────────────

    def _anthropic_loop(self):
        """Core loop using Anthropic API: call model, stream response, handle tool calls."""
        try:
            import anthropic
        except ImportError:
            self.stream_bridge.send_error(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )
            return

        api_key = self.settings.get_password("api_key") if self.settings.api_key else None
        if not api_key:
            self.stream_bridge.send_error(
                "No API key configured. Set it in AI Bot Settings."
            )
            return

        client = anthropic.Anthropic(api_key=api_key)
        max_iterations = self.settings.max_tool_calls_per_turn or 15

        for _ in range(max_iterations):
            api_messages = self._prepare_messages_for_api()

            with client.messages.stream(
                model=self.settings.model_name or "claude-sonnet-4-20250514",
                max_tokens=self.settings.max_tokens_per_request or 4096,
                system=get_system_prompt(self.user, self.company),
                tools=self.tool_registry.get_all_schemas(),
                messages=api_messages,
            ) as stream:
                response = self.stream_bridge.process_stream(stream)

            # Track tokens
            self.token_tracker.record(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_tokens=getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ),
                cache_read_tokens=getattr(
                    response.usage, "cache_read_input_tokens", 0
                ),
                model=self.settings.model_name,
            )

            # Append assistant response
            self.messages.append({
                "role": "assistant",
                "content": self._serialize_content_blocks(response.content),
                "timestamp": frappe.utils.now_datetime().isoformat(),
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            })

            if response.stop_reason != "tool_use":
                self.stream_bridge.send_done()
                break

            # Process tool calls
            tool_results = self._process_tool_calls(response.content)
            self.messages.append({
                "role": "user",
                "content": tool_results,
                "timestamp": frappe.utils.now_datetime().isoformat(),
            })
        else:
            self.stream_bridge.send_error(
                "Maximum tool call limit reached. Please simplify your request."
            )

    def _prepare_messages_for_api(self) -> list:
        """Strip custom metadata keys before sending to Anthropic."""
        cleaned = []
        for msg in self.messages:
            cleaned.append({"role": msg["role"], "content": msg["content"]})

        # Context window management: cap at 100 messages
        if len(cleaned) > 100:
            cleaned = cleaned[:2] + cleaned[-98:]

        return cleaned

    def _serialize_content_blocks(self, content_blocks) -> list:
        """Convert Anthropic SDK content block objects to JSON-serializable dicts."""
        serialized = []
        for block in content_blocks:
            if block.type == "text":
                serialized.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                serialized.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        return serialized

    def _process_tool_calls(self, content_blocks) -> list:
        """Execute tool calls with permission checks, sanitization, and audit."""
        results = []

        for block in content_blocks:
            if block.type != "tool_use":
                continue

            # Clear accumulated messages so permission popups don't leak to client
            if hasattr(frappe.local, "message_log"):
                frappe.local.message_log = []

            self.turn_tool_calls += 1
            tool_name = block.name
            tool_input = block.input
            tool_id = block.id
            start_time = time.time()

            self.stream_bridge.send_tool_start(tool_name, tool_input)

            try:
                # Permission check
                self.permission_guard.check(tool_name, tool_input)

                # Input sanitization
                sanitized_input, blocked_fields = self.sanitizer.sanitize(
                    tool_name, tool_input
                )

                # Subagent spawn
                if tool_name == "meta.spawn_subagent":
                    result = self._handle_subagent(sanitized_input)
                else:
                    tool_fn = self.tool_registry.get_tool(tool_name)
                    result = tool_fn.execute(**sanitized_input)

                exec_time = int((time.time() - start_time) * 1000)

                self._audit_log(
                    tool_name=tool_name,
                    tool_input=sanitized_input,
                    tool_output=result,
                    status="Success",
                    exec_time=exec_time,
                    blocked_fields=blocked_fields,
                )

                self.stream_bridge.send_tool_result(tool_name, result)

                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, default=str),
                })

            except frappe.PermissionError as e:
                exec_time = int((time.time() - start_time) * 1000)
                self._audit_log(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output={"error": str(e)},
                    status="PermissionDenied",
                    exec_time=exec_time,
                )
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"error": f"Permission denied: {e}"}),
                    "is_error": True,
                })

            except Exception as e:
                exec_time = int((time.time() - start_time) * 1000)
                self._audit_log(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output={"error": str(e)},
                    status="Error",
                    exec_time=exec_time,
                )
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"error": str(e)}),
                    "is_error": True,
                })

        return results

    def _handle_subagent(self, params: dict) -> dict:
        if not self.settings.subagent_enabled:
            return {"error": "Subagent spawning is disabled"}

        spawner = SubagentSpawner(
            user=self.user,
            company=self.company,
            parent_session_id=self.session_id,
            token_tracker=self.token_tracker,
            stream_bridge=self.stream_bridge,
            max_depth=self.settings.max_subagent_depth or 2,
        )
        return spawner.run(
            task_description=params["task"],
            tools_needed=params.get("tools", []),
            context=params.get("context", ""),
        )

    def _audit_log(self, tool_name, tool_input, tool_output,
                   status, exec_time, blocked_fields=None):
        """Write an immutable audit log entry."""
        action_type = "Read"
        if "create" in tool_name:
            action_type = "Create"
        elif "update" in tool_name:
            action_type = "Update"
        elif "submit" in tool_name:
            action_type = "Submit"

        output_str = json.dumps(tool_output, default=str)
        if len(output_str) > 10000:
            output_str = output_str[:10000] + "... [truncated]"

        frappe.get_doc({
            "doctype": "AI Audit Log",
            "session": self.session_id,
            "user": self.user,
            "company": self.company,
            "tool_name": tool_name,
            "tool_input_json": json.dumps(tool_input, default=str),
            "tool_output_json": output_str,
            "tool_result_status": status,
            "execution_time_ms": exec_time,
            "doctype_accessed": tool_input.get("doctype", ""),
            "document_name": tool_input.get("name", ""),
            "action_type": action_type,
            "fields_requested": json.dumps(tool_input.get("fields", [])),
            "fields_blocked": json.dumps(blocked_fields or []),
        }).insert(ignore_permissions=True)
        frappe.db.commit()


def run_orchestrator(user: str, session_id: str, message: str, company: str, image_url: str = None):
    """Entry point for background job execution."""
    frappe.set_user(user)
    # Suppress Frappe's popup messages — errors are shown in the AI chat instead.
    # Without this, permission errors from has_permission(throw=True) would show
    # as browser popups in addition to the chat error.
    frappe.flags.mute_messages = True
    if hasattr(frappe.local, "message_log"):
        frappe.local.message_log = []
    try:
        agent = Orchestrator(user=user, session_id=session_id, company=company)
        agent.handle_message(message, image_url=image_url)
    except Exception as e:
        # Clear any accumulated messages so they don't leak to the client
        if hasattr(frappe.local, "message_log"):
            frappe.local.message_log = []
        # Log the full technical error for developers
        frappe.log_error(title="AI Agent Error", message=frappe.get_traceback())

        # Determine a friendly message — never expose raw errors to users
        raw_error = str(e).lower()
        if "permission" in raw_error:
            friendly_msg = "You don't have permission for that action. Ask your admin for access."
        elif "not found" in raw_error:
            friendly_msg = "I couldn't find what you're looking for. Could you double-check the name?"
        elif "timeout" in raw_error or "timed out" in raw_error:
            friendly_msg = "The request took too long. Please try again with a simpler question."
        elif "rate limit" in raw_error or "rate_limit" in raw_error:
            friendly_msg = "The AI service is temporarily busy. Please wait a moment and try again."
        elif "api key" in raw_error or "authentication" in raw_error:
            friendly_msg = "There is a configuration issue with the AI service. Please contact your administrator."
        else:
            friendly_msg = "I ran into an issue processing your request. Please try again."

        frappe.publish_realtime(
            event="ai_error",
            message={"session_id": session_id, "error": friendly_msg},
            user=user,
            after_commit=False,
        )
