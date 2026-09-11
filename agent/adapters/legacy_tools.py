"""
Adapter for wrapping legacy tools from interaction/registry.

This adapter allows the new Agent Runtime to use existing tools
without modifying the legacy system.

Key principle: PRESERVE the original tool result, do not infer success
from text patterns like "SUCESSO".
"""

from typing import Dict, Any, Optional, List
import time
import logging

from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class LegacyToolAdapter(BaseTool):
    """
    Wraps a single legacy tool to make it compatible with new runtime.
    
    Responsibilities:
    - Call the legacy tool's execute() method
    - Convert exception to ToolResult
    - Preserve the original output
    - Document limitations
    """
    
    def __init__(self, legacy_tool: Any):
        """
        Initialize adapter for a legacy tool.
        
        Args:
            legacy_tool: A tool object from interaction/registry with:
                - name: str
                - description: str
                - execute(params) -> result
        
        Note: We do NOT assume any specific interface for legacy tools.
        We try to call execute() and handle whatever it returns.
        """
        super().__init__(
            name=legacy_tool.name,
            description=legacy_tool.description,
        )
        self._legacy_tool = legacy_tool
    
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the legacy tool and wrap result.
        
        The adapter:
        1. Calls the legacy tool's execute() method
        2. Catches exceptions
        3. Returns structured ToolResult
        
        IMPORTANT: We do NOT check for "SUCESSO" in the output.
        If the tool returns a string, we preserve it as-is.
        If it returns without exception, success=True.
        If exception occurs, success=False.
        """
        start_time = time.time()
        
        try:
            # Call legacy tool
            result = self._legacy_tool.execute(params)
            
            # Tool executed without exception -> success
            elapsed_ms = (time.time() - start_time) * 1000
            
            logger.debug(
                f"Legacy tool '{self.name}' executed successfully: {result!r}"
            )
            
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=result,
                execution_time_ms=elapsed_ms,
                metadata={"adapter": "legacy", "legacy_tool": type(self._legacy_tool).__name__},
            )
        
        except Exception as e:
            # Tool raised exception -> failure
            elapsed_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            logger.warning(
                f"Legacy tool '{self.name}' raised exception: {error_msg}"
            )
            
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                execution_time_ms=elapsed_ms,
                metadata={"adapter": "legacy", "legacy_tool": type(self._legacy_tool).__name__},
            )
    
    def get_input_schema(self) -> Dict[str, Any]:
        """
        Get input schema from legacy tool if available.
        
        Falls back to generic schema if legacy tool doesn't expose schema.
        """
        if hasattr(self._legacy_tool, 'get_input_schema'):
            try:
                return self._legacy_tool.get_input_schema()
            except Exception:
                pass
        
        # Fallback: generic schema
        return {
            "type": "object",
            "properties": {
                "params": {"type": "object"}
            },
            "required": [],
        }


class LegacyToolsAdapter:
    """
    Wraps a collection of legacy tools (from interaction/registry).
    
    This adapter allows the new registry to discover and use
    existing tools without any modification to the legacy system.
    """
    
    def __init__(self, legacy_registry: Any):
        """
        Initialize adapter for a legacy registry.
        
        Args:
            legacy_registry: Object with list_tools() or similar method
                that returns legacy tool objects.
        
        Note: Tries multiple methods to discover tools:
        - all_tools()
        - list_tools()
        - tools property
        """
        self._legacy_registry = legacy_registry
        self._tools: Dict[str, LegacyToolAdapter] = {}
        self._discover_tools()
    
    def _discover_tools(self) -> None:
        """Discover tools from legacy registry."""
        legacy_tools = []
        
        # Try various interfaces to get tools
        if hasattr(self._legacy_registry, 'all_tools'):
            try:
                legacy_tools = self._legacy_registry.all_tools()
            except Exception as e:
                logger.warning(f"Failed to call all_tools(): {e}")
        
        elif hasattr(self._legacy_registry, 'list_tools'):
            try:
                legacy_tools = self._legacy_registry.list_tools()
            except Exception as e:
                logger.warning(f"Failed to call list_tools(): {e}")
        
        elif hasattr(self._legacy_registry, 'tools'):
            try:
                legacy_tools = self._legacy_registry.tools
            except Exception as e:
                logger.warning(f"Failed to access tools property: {e}")
        
        # Wrap discovered tools
        for tool in legacy_tools:
            try:
                adapter = LegacyToolAdapter(tool)
                self._tools[adapter.name] = adapter
                logger.debug(f"Adapted legacy tool: {adapter.name}")
            except Exception as e:
                logger.warning(f"Failed to adapt tool {tool}: {e}")
    
    def get_adapted_tools(self) -> List[LegacyToolAdapter]:
        """Get all adapted tools."""
        return list(self._tools.values())
    
    def get_adapted_tool(self, name: str) -> Optional[LegacyToolAdapter]:
        """Get specific adapted tool by name."""
        return self._tools.get(name)
    
    def count(self) -> int:
        """Get number of adapted tools."""
        return len(self._tools)
    
    def describe(self) -> str:
        """Human-readable description."""
        return f"LegacyToolsAdapter({self.count()} tools)"
