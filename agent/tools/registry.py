"""
Tool Registry: Central registry of available tools.

Manages tool discovery, validation, and schema generation.
Implementation-agnostic (no dependency on OpenAI, LLM, or specific tools).
"""

from typing import Dict, List, Optional
from agent.tools.base import BaseTool


class AgentToolRegistry:
    """
    Registry of tools available to the agent.
    
    Responsibilities:
    - Register tools
    - Find tools by name
    - List all tools
    - Prevent duplicate registrations
    - Generate tool schemas
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """
        Register a tool.
        
        Args:
            tool: BaseTool instance to register
        
        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' already registered. "
                f"Use unregister() first if you want to replace it."
            )
        
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.
        
        Args:
            name: Tool name to unregister
        
        Returns:
            True if tool was found and unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def find(self, name: str) -> Optional[BaseTool]:
        """
        Find a tool by name.
        
        Args:
            name: Tool name to find
        
        Returns:
            BaseTool if found, None otherwise
        """
        return self._tools.get(name)
    
    def exists(self, name: str) -> bool:
        """Check if a tool with given name exists."""
        return name in self._tools
    
    def list_tools(self) -> List[BaseTool]:
        """
        Get all registered tools.
        
        Returns:
            List of BaseTool instances (in registration order)
        """
        return list(self._tools.values())
    
    def get_names(self) -> List[str]:
        """Get names of all registered tools."""
        return list(self._tools.keys())
    
    def count(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)
    
    def get_schemas(self) -> Dict[str, Dict]:
        """
        Get input schemas for all tools.
        
        Returns:
            Dict mapping tool name -> schema
        """
        schemas = {}
        for name, tool in self._tools.items():
            schemas[name] = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.get_input_schema(),
            }
        return schemas
    
    def describe(self) -> str:
        """Human-readable description of registry."""
        names = ", ".join(self.get_names())
        return f"AgentToolRegistry({self.count()} tools: {names})"
