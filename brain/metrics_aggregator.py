#!/usr/bin/env python3
"""
brain/metrics_aggregator.py — Agregador de Métricas (Luna v1.4.1 Stabilization)
Coleta estatísticas do Planner, Memória, EventBus e Ferramentas para gerar o painel Luna Debug.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("luna.metrics")

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

class MetricsAggregator:
    def __init__(self):
        self.trace_logger = None
        self.event_bus = None
        
        try:
            from brain.trace_logger import get_trace_logger
            self.trace_logger = get_trace_logger()
        except ImportError:
            pass
            
        try:
            from brain.event_bus import get_event_bus
            self.event_bus = get_event_bus()
        except ImportError:
            pass

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Agrega todas as métricas para o Luna Debug."""
        metrics = {
            "planner": {"success": 0, "failed": 0, "total": 0, "success_rate": 0.0},
            "reflection": {"success": 0, "failed": 0, "total": 0, "success_rate": 0.0},
            "tools": {},
            "memory": {"episodes": 0, "profile_items": 0, "goals": 0},
            "performance": {"avg_latency": 0.0, "total_traces": 0}
        }
        
        self._aggregate_traces(metrics)
        self._aggregate_memory(metrics)
        return metrics
        
    def _aggregate_traces(self, metrics: Dict[str, Any]):
        if not self.trace_logger:
            return
            
        stats = self.trace_logger.get_stats()
        metrics["performance"]["total_traces"] = stats.get("total_traces", 0)
        metrics["performance"]["avg_latency"] = stats.get("avg_latency", 0.0)
        
        # We deduce planner and reflection from recent traces for a quick summary
        traces = self.trace_logger.get_recent_traces(limit=50)
        tool_counts = {}
        
        for t in traces:
            steps = t.get("steps", [])
            for step in steps:
                step_type = step.get("step_type", "")
                tool_name = step.get("tool_name", "")
                success = step.get("success", False)
                
                if tool_name:
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                    
                if step_type == "planner":
                    metrics["planner"]["total"] += 1
                    if success:
                        metrics["planner"]["success"] += 1
                    else:
                        metrics["planner"]["failed"] += 1
                        
                elif step_type == "reflection":
                    metrics["reflection"]["total"] += 1
                    if success:
                        metrics["reflection"]["success"] += 1
                    else:
                        metrics["reflection"]["failed"] += 1

        if metrics["planner"]["total"] > 0:
            metrics["planner"]["success_rate"] = round(metrics["planner"]["success"] / metrics["planner"]["total"] * 100, 1)
            
        if metrics["reflection"]["total"] > 0:
            metrics["reflection"]["success_rate"] = round(metrics["reflection"]["success"] / metrics["reflection"]["total"] * 100, 1)
            
        # Top 5 tools
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        metrics["tools"] = dict(sorted_tools)

    def _aggregate_memory(self, metrics: Dict[str, Any]):
        # Episodic Memory — usa API pública get_episode_count()
        try:
            from brain.episodic_memory import get_episodic_memory
            episodic = get_episodic_memory()
            metrics["memory"]["episodes"] = episodic.get_episode_count()
        except ImportError:
            logger.debug("Módulo episodic_memory não disponível.")
        except Exception as e:
            logger.warning(f"Erro ao agregar memória episódica: {e}")

        # User Model (Profile)
        try:
            from brain.user_model import get_user_model
            user_model = get_user_model()
            count = 0
            for v in user_model.profile.values():
                if isinstance(v, list):
                    count += len(v)
                elif isinstance(v, dict):
                    count += len(v.keys())
                elif v:
                    count += 1
            metrics["memory"]["profile_items"] = count
        except ImportError:
            logger.debug("Módulo user_model não disponível.")
        except AttributeError as e:
            logger.warning(f"Atributo inesperado no user_model (API mudou?): {e}")
        except Exception as e:
            logger.warning(f"Erro ao agregar perfil do usuário: {e}")

        # Goals
        try:
            goals_file = Path(__file__).parent.parent / "config" / "goals.json"
            if goals_file.exists():
                goals_data = json.loads(goals_file.read_text(encoding="utf-8"))
                metrics["memory"]["goals"] = len(goals_data)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Erro ao ler goals.json: {e}")
        except Exception as e:
            logger.warning(f"Erro inesperado ao agregar goals: {e}")

def get_metrics_aggregator():
    return MetricsAggregator()
