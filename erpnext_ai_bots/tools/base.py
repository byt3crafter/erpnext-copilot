from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseTool(ABC):
    """Base class for all agent tools.

    Every tool has:
    - A namespaced name (e.g. "accounting.get_trial_balance")
    - A description for the model
    - An input schema (JSON Schema)
    - An execute method
    - An action_type for audit classification
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    required_params: List[str] = []

    # For audit logging
    action_type: str = "Read"  # Read | Create | Update | Submit | Cancel | Report

    # For permission checking
    required_doctype: Optional[str] = None
    required_ptype: str = "read"

    def __init__(self, user: str = None, company: str = None):
        self.user = user
        self.company = company

    def schema(self) -> dict:
        """Return the tool definition in Anthropic function-calling format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params,
            },
        }

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        """Execute the tool and return a JSON-serializable dict."""
        ...
