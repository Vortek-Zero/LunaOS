#!/usr/bin/env python3
"""
brain/planner.py — Divide pedidos compostos em passos antes de executar.

Ex.: "abra o firefox e pesquise youtube.com" → 2 passos, executados em ordem.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List

# Conectores que separam ordens distintas (não confundir com "e" dentro de palavras)
_SPLIT_RE = re.compile(
    r"\s+e\s+"
    r"|\s*,\s*depois\s+"
    r"|\s+depois\s+"
    r"|\s+então\s+"
    r"|\s+em seguida\s+"
    r"|\s*;\s*"
    r"|\s*,\s+e\s+",
    re.IGNORECASE,
)

# Frases que indicam múltiplas tarefas mesmo sem "e"
_MULTI_HINTS = (
    " e ",
    " depois ",
    " então ",
    " em seguida ",
    ";",
    ", depois",
)


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def split_steps(text: str) -> List[str]:
    """Quebra mensagem em passos independentes."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = _SPLIT_RE.split(raw)
    steps = [p.strip() for p in parts if p.strip()]
    return steps if steps else [raw]


def is_multi_step(text: str) -> bool:
    """True se há mais de uma ordem na mesma frase."""
    steps = split_steps(text)
    if len(steps) > 1:
        return True
    tl = _norm(text)
    return any(h in tl for h in _MULTI_HINTS) and len(steps) >= 1 and len(text) > 25


def format_plan(text: str) -> str:
    """Texto de plano para injetar no prompt do agente."""
    steps = split_steps(text)
    if len(steps) <= 1:
        return ""
    lines = [f"PLANO ({len(steps)} passos — execute TODOS antes de responder):"]
    for i, s in enumerate(steps, 1):
        lines.append(f"  {i}. {s}")
    lines.append("Não pare após o passo 1. Confirme cada passo na resposta final.")
    return "\n".join(lines)


def step_count(text: str) -> int:
    return len(split_steps(text))
