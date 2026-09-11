"""
Agent Runtime - Foundation Layer

This module provides the core abstractions for a modern Computer-Using Agent.
It runs alongside the legacy system without modifying it.

Key concepts:
- Observation: What the agent sees
- Action: What the agent wants to do
- Environment: Interface between agent and world
- Tool: Capability abstraction
"""

from agent.environment.observation import Observation
from agent.environment.action import Action
from agent.environment.base import Environment
from agent.tools.base import BaseTool, ToolResult
from agent.tools.registry import AgentToolRegistry

__all__ = [
    "Observation",
    "Action",
    "Environment",
    "BaseTool",
    "ToolResult",
    "AgentToolRegistry",
]

__version__ = "0.1.0-m1"
