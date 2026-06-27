"""
brain/loop_guard.py — Detecção e prevenção de loops infinitos de ferramentas (inspirado no OpenJarvis)
Previne que o agente entre em ciclos degenerados de tool_calls.
"""
import hashlib
import re
from collections import deque
from typing import Optional


class LoopVerdict:
    """Resultado de uma verificação do loop guard."""
    def __init__(self, blocked: bool = False, reason: str = "", warned: bool = False):
        self.blocked = blocked
        self.reason = reason
        self.warned = warned


class LoopGuard:
    """
    Detecta e previne loops degenerados de ferramentas.

    Características:
    1. Hash tracking: SHA-256 de (tool_name, args) bloqueia após N chamadas idênticas
    2. Ping-pong: Janela deslizante detecta padrões A-B-A-B ou A-B-C-A-B-C
    3. Budget por ferramenta: Limite de chamadas por ferramenta
    4. Compressão de contexto: 4 estágios de recuperação de overflow
    """

    def __init__(
        self,
        max_identical_calls: int = 3,
        ping_pong_window: int = 6,
        poll_tool_budget: int = 5,
        max_context_messages: int = 100,
        warn_before_block: bool = True,
    ):
        self._max_identical = max_identical_calls
        self._ping_pong_window = ping_pong_window
        self._poll_budget = poll_tool_budget
        self._max_context = max_context_messages
        self._warn_before_block = warn_before_block

        self._call_counts: dict[str, int] = {}
        self._tool_sequence: deque[str] = deque(maxlen=ping_pong_window * 2)
        self._per_tool_counts: dict[str, int] = {}
        self._warned_cycles: set[str] = set()

    def check_call(self, tool_name: str, arguments: str) -> LoopVerdict:
        """Verifica se uma chamada de ferramenta deve prosseguir ou ser bloqueada."""
        return self._python_check(tool_name, arguments)

    def _python_check(self, tool_name: str, arguments: str) -> LoopVerdict:
        # 1. Hash tracking — chamadas idênticas
        call_hash = hashlib.sha256(
            f"{tool_name}:{arguments}".encode()
        ).hexdigest()[:16]
        self._call_counts[call_hash] = self._call_counts.get(call_hash, 0) + 1
        if self._call_counts[call_hash] > self._max_identical:
            reason = (
                f"Chamada idêntica a '{tool_name}' repetida "
                f"{self._call_counts[call_hash]} vezes "
                f"(máx {self._max_identical})."
            )
            return self._wrap_verdict(LoopVerdict(blocked=True, reason=reason))

        # 2. Budget por ferramenta — sliding window (last 20 calls)
        window_size = max(self._ping_pong_window * 3, 20)
        recent_tools = list(self._tool_sequence)[-window_size:]
        recent_count = recent_tools.count(tool_name)
        if recent_count > self._poll_budget:
            reason = (
                f"Ferramenta '{tool_name}' excedeu o budget "
                f"({self._poll_budget} nas últimas {window_size} chamadas)."
            )
            return self._wrap_verdict(LoopVerdict(blocked=True, reason=reason))
        self._per_tool_counts[tool_name] = recent_count + 1

        # 3. Ping-pong detection
        self._tool_sequence.append(tool_name)
        if len(self._tool_sequence) >= self._ping_pong_window:
            if self._detect_ping_pong():
                reason = "Padrão repetitivo de ferramentas detectado (ping-pong)."
                return self._wrap_verdict(LoopVerdict(blocked=True, reason=reason))

        return LoopVerdict()

    def _wrap_verdict(self, verdict: LoopVerdict) -> LoopVerdict:
        """Aplica lógica warn-before-block."""
        if verdict.blocked and self._warn_before_block:
            cycle_key = verdict.reason
            # Extrai tool_name estável do reason para chave consistente
            tool_match = re.search(r"'([\w.]+)'", cycle_key)
            stable_key = tool_match.group(1) if tool_match else cycle_key
            if stable_key not in self._warned_cycles:
                self._warned_cycles.add(stable_key)
                verdict.warned = True
                return verdict  # Still blocked, but with warned=True
        return verdict

    def _detect_ping_pong(self) -> bool:
        """Detecta padrões repetitivos na sequência de ferramentas."""
        seq = list(self._tool_sequence)
        n = len(seq)
        # Period 1: same tool repeated (AAAA)
        if n >= 4:
            if len(set(seq[-4:])) == 1:
                return True
        for period in (2, 3):
            if n >= period * 2:
                tail = seq[-period * 2:]
                pattern = tail[:period]
                if all(tail[i] == pattern[i % period] for i in range(len(tail))):
                    return True
        return False

    def compress_messages(self, messages: list[dict]) -> list[dict]:
        """Aplica compressão de contexto quando o número de mensagens excede o limite."""
        if len(messages) <= self._max_context:
            return messages

        # Stage 1: Trunca resultados de ferramentas antigos
        threshold = len(messages) // 2
        compressed = []
        for i, msg in enumerate(messages):
            if i < threshold and msg.get("role") == "tool":
                compressed.append({
                    "role": "tool",
                    "content": "[Resultado truncado]",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "name": msg.get("name"),
                })
            else:
                compressed.append(msg)

        if len(compressed) <= self._max_context:
            return compressed

        # Stage 2: Janela deslizante — mantém system + recentes
        system_msgs = [m for m in compressed if m.get("role") == "system"]
        non_system = [m for m in compressed if m.get("role") != "system"]
        window_size = self._max_context - len(system_msgs)
        if len(non_system) > window_size:
            non_system = non_system[-window_size:]
        compressed = system_msgs + non_system

        if len(compressed) <= self._max_context:
            return compressed

        # Stage 3: Remove pares tool_call/result do meio
        keep_start = max(len(system_msgs), len(compressed) // 10)
        keep_end = len(compressed) // 2
        if keep_start + keep_end > len(compressed):
            keep_end = len(compressed) - keep_start
        compressed = compressed[:keep_start] + compressed[-keep_end:] if keep_end > 0 else compressed[:keep_start]

        if len(compressed) <= self._max_context:
            return compressed

        # Stage 4: Extreme — system + últimas 2 trocas
        sys_final = [m for m in compressed if m.get("role") == "system"]
        tail = [m for m in compressed if m.get("role") != "system"]
        return sys_final + tail[-4:]

    def reset(self) -> None:
        """Reseta todo o estado de rastreamento."""
        self._call_counts.clear()
        self._tool_sequence.clear()
        self._per_tool_counts.clear()
        self._warned_cycles.clear()
