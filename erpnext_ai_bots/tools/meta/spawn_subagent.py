from erpnext_ai_bots.tools.base import BaseTool


class SpawnSubagentTool(BaseTool):
    """Meta tool that the orchestrator uses to spawn a subagent.
    The actual spawning logic is handled by the orchestrator, not this tool.
    This class only defines the schema presented to the model.
    """

    name = "meta.spawn_subagent"
    description = (
        "Spawn a focused subagent to handle a complex multi-step workflow. "
        "Use this ONLY when a task requires 4+ sequential tool calls that form "
        "a logical workflow. Examples: creating a full purchase cycle, processing "
        "month-end closing, onboarding a new employee with all related documents. "
        "Do NOT use for simple queries or single-step operations."
    )
    parameters = {
        "task": {
            "type": "string",
            "description": "Clear description of the multi-step task",
        },
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tool namespaces needed, e.g. ['accounting.*', 'core.create_document']",
        },
        "context": {
            "type": "string",
            "description": "Relevant context from the current conversation",
        },
    }
    required_params = ["task", "tools"]
    action_type = "Read"

    def execute(self, **kwargs):
        # This is never called directly — the orchestrator intercepts it
        raise NotImplementedError("Subagent spawning is handled by the orchestrator")
