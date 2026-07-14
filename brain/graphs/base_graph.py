#!/usr/bin/env python3
"""
brain/graphs/base_graph.py — Orquestração de workflows complexos via LangGraph.
"""

import os
import sys

# Ajusta path para importar LangGraph da pasta libs
LANGGRAPH_PATH = os.path.abspath(os.path.join(os.getcwd(), "langgraph/libs/langgraph"))
if LANGGRAPH_PATH not in sys.path:
    sys.path.append(LANGGRAPH_PATH)

try:
    import operator
    from typing import Annotated, List, TypedDict, Union

    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


class AgentState(TypedDict):
    """Estado do workflow da Luna."""

    messages: Annotated[list[str], operator.add]
    next_step: str
    final_answer: str


class LunaGraphOrchestrator:
    def __init__(self):
        self.builder = None
        if HAS_LANGGRAPH:
            self.builder = StateGraph(AgentState)
            self._build_basic_graph()

    def _build_basic_graph(self):
        """Constrói um grafo básico de decisão."""
        # Aqui definiremos os nós conforme a necessidade
        pass

    def run_workflow(self, initial_state: dict):
        if not HAS_LANGGRAPH:
            return "FALHOU: LangGraph não está configurado corretamente."
        # Execução do grafo
        return "Worklfow em desenvolvimento."


_instance = None


def get_graph_orchestrator():
    global _instance
    if _instance is None:
        _instance = LunaGraphOrchestrator()
    return _instance
