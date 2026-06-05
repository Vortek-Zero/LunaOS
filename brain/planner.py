#!/usr/bin/env python3
"""
brain/planner.py — Camada 1: Planner (Llama 70B - Groq)
Responsável por entender o pedido e criar um plano estratégico em JSON.
Não chama ferramentas.
"""
import json
import logging
from typing import Dict, Any, Optional

from brain.llm import get_llm, GROQ_MODELS

logger = logging.getLogger("luna.planner")

PLANNER_PROMPT = """Você é o Planner da Luna. Sua função é criar um plano estratégico para resolver o pedido do usuário.
Você deve retornar APENAS um JSON válido seguindo este formato:

{
  "analysis": "Breve análise do que o usuário quer",
  "goal": "Objetivo final claro",
  "plan": [
    "Passo 1...",
    "Passo 2..."
  ],
  "complexity": "low|medium|high",
  "needs_tools": true|false,
  "potential_challenges": "Quaisquer desafios previstos",
  "reasoning": "Sua lógica para este plano"
}

REGRAS:
1. Responda APENAS o JSON. Sem textos antes ou depois.
2. O plano deve ser focado em ações que podem ser executadas por um agente com acesso ao PC e Web.
3. Se o pedido for apenas conversa, defina "needs_tools": false.
"""

def _repair_json(text: str) -> str:
    """Tenta reparar JSON truncado ou malformado de forma agressiva."""
    text = text.strip()
    
    # Remove markdown blocks se existirem
    if "```" in text:
        parts = text.split("```")
        # Pega a parte que contém o JSON (usualmente a do meio)
        text = next((p for p in parts if p.strip().startswith("{")), parts[0])
        text = text.replace("json", "").strip()
    
    # Garante que começa com { e termina com }
    if not text.startswith("{"): text = "{" + text
    if not text.endswith("}"): text = text + "}"
    
    # Se ainda tiver uma string não fechada, tenta fechar artificialmente
    # (isso é um fallback extremo para evitar o erro de 'Unterminated string')
    try:
        json.loads(text)
    except json.JSONDecodeError:
        # Se falhar, limpa caracteres de controle comuns
        text = text.replace("\n", " ").replace("\r", " ")
        # Tenta fechar aspas abertas se for o erro (simplista mas ajuda)
        if text.count('"') % 2 != 0:
             text += '"'
    return text

def generate_plan(user_input: str, context: str = "") -> Dict[str, Any]:
    """
    Gera um plano estratégico usando Llama 70B com reparo de JSON.
    """
    llm = get_llm()
    
    messages = [
        {"role": "system", "content": PLANNER_PROMPT},
        {"role": "user", "content": f"Contexto Recente:\n{context}\n\nPedido do Usuário: {user_input}\n\nResponda APENAS o JSON puro:"}
    ]
    
    model = GROQ_MODELS.get("heavy", "llama-3.3-70b-versatile")
    
    try:
        raw_response = llm.generate(messages=messages, task_type="planning", model=model)
        content = raw_response.get("message", {}).get("content", "") if isinstance(raw_response, dict) else raw_response
        
        # Repara e limpa
        repaired_content = _repair_json(content)
        return json.loads(repaired_content)
        
    except Exception as e:
        logger.error(f"Erro no Planner: {e}. Raw: {content[:100]}")
        return {
            "analysis": "Erro no planejamento.",
            "goal": user_input,
            "plan": [f"Executar: {user_input}"],
            "complexity": "medium",
            "needs_tools": True,
            "reasoning": "Fallback de erro."
        }

def format_plan_for_prompt(plan_json: Dict[str, Any]) -> str:
    """Formata o plano JSON para ser incluído no prompt do Executor."""
    steps = "\n".join([f"- {s}" for s in plan_json.get("plan", [])])
    return (
        f"\n[PLANO ESTRATÉGICO]\n"
        f"Objetivo: {plan_json.get('goal')}\n"
        f"Passos:\n{steps}\n"
        f"Análise: {plan_json.get('analysis')}\n"
    )

# Para manter compatibilidade temporária com o resto do código se necessário
def split_steps(text: str):
    return [text]

def is_multi_step(text: str):
    return False

def format_plan(text: str):
    return ""

def step_count(text: str):
    return 1
