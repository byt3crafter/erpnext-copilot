import frappe
import json
from erpnext_ai_bots.tools.registry import ToolRegistry
from erpnext_ai_bots.agent.prompts import get_subagent_prompt


class SubagentSpawner:
    """Spawns a focused subagent for complex multi-step tasks.

    The subagent:
    - Gets a SUBSET of tools (only what it needs)
    - Has its own focused system prompt
    - Runs a tool-use loop to completion
    - Returns a structured result to the orchestrator
    - All token usage is tracked under the parent session
    """

    def __init__(self, user, company, parent_session_id,
                 token_tracker, stream_bridge, max_depth=2, current_depth=0):
        self.user = user
        self.company = company
        self.parent_session_id = parent_session_id
        self.token_tracker = token_tracker
        self.stream_bridge = stream_bridge
        self.max_depth = max_depth
        self.current_depth = current_depth

        try:
            import anthropic
        except ImportError:
            frappe.throw(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )

        settings = frappe.get_cached_doc("AI Bot Settings")
        self.client = anthropic.Anthropic(api_key=settings.get_password("api_key"))
        self.model = settings.model_name or "claude-sonnet-4-20250514"
        self.tool_registry = ToolRegistry(user=self.user, company=self.company)

    def run(self, task_description: str, tools_needed: list,
            context: str = "") -> dict:
        """Execute a subagent task to completion."""
        if self.current_depth >= self.max_depth:
            return {
                "status": "error",
                "result": "Maximum subagent nesting depth reached",
            }

        tools = self.tool_registry.resolve_tool_subset(tools_needed)
        tool_schemas = [t.schema() for t in tools]

        messages = [{
            "role": "user",
            "content": (
                f"TASK: {task_description}\n\n"
                f"CONTEXT FROM CONVERSATION:\n{context}\n\n"
                "Complete this task step by step. Use the provided tools. "
                "When done, provide a summary of what you accomplished."
            ),
        }]

        system_prompt = get_subagent_prompt(self.user, self.company)
        steps = []
        max_iterations = 10

        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=tool_schemas,
                messages=messages,
            )

            self.token_tracker.record(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=self.model,
                is_subagent=True,
            )

            messages.append({
                "role": "assistant",
                "content": response.content,
            })

            if response.stop_reason != "tool_use":
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                return {
                    "status": "completed",
                    "result": final_text,
                    "steps_taken": len(steps),
                    "tools_called": [s["tool"] for s in steps],
                }

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool = self.tool_registry.get_tool(block.name)
                try:
                    result = tool.execute(**block.input)
                    steps.append({"tool": block.name, "status": "success"})
                except Exception as e:
                    result = {"error": str(e)}
                    steps.append({"tool": block.name, "status": "error"})

                self.stream_bridge.send_tool_start(block.name, block.input)
                self.stream_bridge.send_tool_result(block.name, result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

        return {
            "status": "max_iterations",
            "result": "Subagent reached maximum iterations",
            "steps_taken": len(steps),
        }
