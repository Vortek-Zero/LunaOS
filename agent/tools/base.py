"""
Tool: Capability abstraction for the agent.

A Tool represents a capability the agent can invoke.
Success/failure is explicit and typed, not inferred from text.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolResult:
    """
    Structured result from executing a tool.
    
    Success is explicit (True/False), not inferred from "SUCESSO" strings.
    """
    
    tool_name: str
    """Name of the tool that was executed."""
    
    success: bool
    """Whether the tool executed successfully (explicit, not inferred)."""
    
    output: Any = None
    """Result data from the tool execution."""
    
    error: Optional[str] = None
    """Error message if success=False."""
    
    execution_time_ms: float = 0.0
    """How long the tool took to execute."""
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Tool-specific metadata."""
    
    timestamp: datetime = field(default_factory=datetime.now)
    """When execution completed."""
    
    def __post_init__(self):
        """Validate result consistency."""
        if not self.success and not self.error:
            raise ValueError("If success=False, error must be provided")
    
    def describe(self) -> str:
        """Human-readable description."""
        status = "OK" if self.success else "FAILED"
        return f"{status}: {self.tool_name} ({self.execution_time_ms:.0f}ms)"


class BaseTool(ABC):
    """
    Abstract base class for a tool.
    
    A tool is a capability the agent can invoke to affect the world.
    Tools are implementation-agnostic (not tied to PyAutoGUI, Selenium, etc).
    """
    
    def __init__(self, name: str, description: str):
        """
        Initialize a tool.
        
        Args:
            name: Unique name of the tool (e.g., 'click', 'type', 'open_browser')
            description: Human-readable description of what it does
        """
        self.name = name
        self.description = description
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute this tool with the given parameters.
        
        Args:
            params: Tool-specific parameters
        
        Returns:
            ToolResult: Structured result (success/error explicitly typed)
        
        Contract:
            - Never raises exceptions (return ToolResult with success=False)
            - Always return a ToolResult
            - If exception occurs, catch it and set success=False + error message
            - NEVER infer success from text like "SUCESSO"
            - ALWAYS set success explicitly
        """
        pass
    
    def get_input_schema(self) -> Dict[str, Any]:
        """
        Return JSON Schema describing tool inputs.
        
        Override this if tool accepts structured parameters.
        
        Returns:
            Dict with 'type', 'properties', 'required' (JSON Schema format)
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }
    
    def describe(self) -> str:
        """Human-readable description."""
        return f"{self.name}: {self.description}"
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"
