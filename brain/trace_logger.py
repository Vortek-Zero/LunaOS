"""
brain/trace_logger.py — Gravação de interações para aprendizado (inspirado no OpenJarvis TraceStore)
Registra cada interação do usuário + ferramentas + resultado em JSONL para análise posterior.
"""
import json
import time
import os
from pathlib import Path
from typing import Optional


TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"


class TraceLogger:
    """
    Logger de traços de interação formato JSONL.
    Cada linha = uma interação completa com metadados.

    Útil para:
    - Analisar padrões de uso
    - Debug de loops/problemáticos
    - Coletar dados para fine-tuning
    - Identificar queries que sempre falham
    """

    def __init__(self, trace_dir: str | Path = TRACE_DIR):
        self._dir = Path(trace_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session_id = f"session_{int(time.time())}"
        self._current_trace: Optional[dict] = None

    def start_trace(self, query: str, context: str = "") -> str:
        """Inicia um novo trace para uma interação."""
        trace_id = f"trace_{int(time.time() * 1000)}_{os.urandom(2).hex()}"
        self._current_trace = {
            "trace_id": trace_id,
            "session_id": self._session_id,
            "timestamp": time.time(),
            "query": query,
            "context_preview": context[:500] if context else "",
            "steps": [],
            "outcome": None,
            "total_latency": 0.0,
            "model_used": "",
        }
        self._start_time = time.time()
        return trace_id

    def add_step(self, step_type: str, tool_name: str = "",
                 arguments: str = "", result: str = "",
                 success: bool = False) -> None:
        """Adiciona um passo (tool_call, generate, etc) ao trace atual."""
        if self._current_trace is None:
            return
        self._current_trace["steps"].append({
            "step_type": step_type,
            "tool_name": tool_name,
            "arguments": arguments[:500],
            "result_preview": result[:500],
            "success": success,
            "timestamp": time.time(),
        })

    def set_model(self, model: str) -> None:
        if self._current_trace is not None:
            self._current_trace["model_used"] = model

    def finish_trace(self, outcome: str, response: str = "") -> Optional[str]:
        """Finaliza e salva o trace atual. Retorna trace_id ou None se falhou."""
        if self._current_trace is None:
            return None
        elapsed = time.time() - self._start_time if hasattr(self, '_start_time') else 0.0
        self._current_trace["outcome"] = outcome
        self._current_trace["total_latency"] = round(elapsed, 3)
        self._current_trace["response_preview"] = response[:500] if response else ""

        trace_id = self._current_trace["trace_id"]

        today_file = self._dir / f"traces_{time.strftime('%Y%m%d')}.jsonl"
        try:
            with open(today_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._current_trace, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[TraceLogger] Erro ao salvar trace: {e}")
            return None
        finally:
            self._current_trace = None

        return trace_id

    def get_recent_traces(self, limit: int = 20) -> list[dict]:
        """Retorna os traces mais recentes."""
        traces = []
        for f in sorted(self._dir.glob("traces_*.jsonl"), reverse=True)[:3]:
            with open(f, "r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if line:
                        try:
                            traces.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return traces[-limit:]

    def get_failed_traces(self, limit: int = 20) -> list[dict]:
        """Retorna traces com falha para análise."""
        all_traces = self.get_recent_traces(limit * 5)
        failed = [t for t in all_traces if t.get("outcome") in ("error", "loop_blocked")]
        return failed[-limit:]

    def get_stats(self) -> dict:
        """Estatísticas básicas dos traces."""
        total = 0
        by_outcome: dict[str, int] = {}
        by_model: dict[str, int] = {}
        total_latency = 0.0

        for f in sorted(self._dir.glob("traces_*.jsonl"), reverse=True)[:5]:
            with open(f, "r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        t = json.loads(line)
                        total += 1
                        outcome = t.get("outcome", "unknown")
                        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
                        model = t.get("model_used", "unknown")
                        by_model[model] = by_model.get(model, 0) + 1
                        total_latency += t.get("total_latency", 0.0)
                    except json.JSONDecodeError:
                        continue

        return {
            "total_traces": total,
            "by_outcome": by_outcome,
            "by_model": by_model,
            "avg_latency": round(total_latency / total, 2) if total else 0.0,
        }

    def get_session_id(self) -> str:
        return self._session_id


# Singleton
_logger: Optional[TraceLogger] = None


def get_trace_logger() -> TraceLogger:
    global _logger
    if _logger is None:
        _logger = TraceLogger()
    return _logger
