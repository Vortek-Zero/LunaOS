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

PLANNER_PROMPT = """Você é o Planner da Luna, um agente de IA de alto desempenho focado em GESTÃO DE RESULTADOS (DOM - Desired Outcome Management).
Sua missão é criar ou ajustar um plano estratégico para resolver o pedido do usuário.

Você opera em um loop RECURSIVO. Em cada iteração, você receberá o pedido original e os RESULTADOS DOS PASSOS ANTERIORES.
Analise se o objetivo foi atingido. Se sim, defina "needs_tools": false e informe na análise que a tarefa foi concluída.

REGRAS CRÍTICAS:
1. CRIAÇÃO DE CÓDIGO/PROJETOS: Se o usuário pedir para CRIAR algo (código, arquivo, projeto, site, app, script, programa, sistema), SEMPRE use "needs_tools": true. Criar algo REAL requer ferramentas — não é conversa.
2. VERIFICAÇÃO/CONSULTA DE PROJETOS: Se o usuário pedir para CHECAR/VERIFICAR/VER o estado de um projeto, pasta ou arquivo ('como está', 'o que tem', 'mostra', 'lista', 'status do projeto'), SEMPRE use "needs_tools": true. Você PRECISA usar check_project ou filesystem para ler o que existe de verdade — NUNCA invente.
3. MATEMÁTICA E CONHECIMENTO: Cálculos básicos (10+10), conversão de unidades simples e perguntas de conhecimento geral NÃO precisam de ferramentas. Defina "needs_tools": false para estes casos.
4. FOCO NO RESULTADO: Se algo falhou, planeje um caminho alternativo ou correção.
5. AGÊNCIA: O plano deve usar as capacidades do PC (Terminal, Arquivos, Browser, UI) apenas quando necessário para interagir com o mundo real.
6. Se a meta foi atingida ou pode ser resolvida apenas com conversa, use "needs_tools": false.

Você deve retornar APENAS um JSON válido:
{
  "analysis": "Análise do estado atual da tarefa. Se concluída ou se for apenas conversa/matemática, diga 'Tarefa concluída ou resolvida por chat'.",
  "goal": "Objetivo final claro",
  "plan": [
    "Próximo passo imediato...",
    "Passos seguintes (opcional)..."
  ],
  "complexity": "low|medium|high",
  "needs_tools": true|false,
  "reasoning": "Por que este é o melhor caminho agora?"
}
"""

def _repair_json(text: str) -> str:
    """Tenta reparar JSON truncado ou malformado de forma agressiva."""
    if not text:
        return "{}"
    text = text.strip()

    # Remove markdown blocks se existirem
    if "```" in text:
        parts = text.split("```")
        text = next((p for p in parts if p.strip().startswith("{") or p.strip().startswith("[")), parts[0])
        text = text.replace("json", "").strip()

    # Extrai o primeiro bloco JSON { ... } via regex (remove texto antes/depois)
    import re
    m = re.search(r'(\{.*\})', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    else:
        # Tenta extrair array
        m = re.search(r'(\[.*\])', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            return "{}"

    # Se ainda tiver uma string não fechada, tenta fechar artificialmente
    try:
        json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("\n", " ").replace("\r", " ")
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
    
    content = ""
    try:
        raw_response = llm.generate(messages=messages, task_type="planning", model=model)
        content = raw_response.get("message", {}).get("content", "") if isinstance(raw_response, dict) else (raw_response or "")
        
        # Repara e limpa
        repaired_content = _repair_json(str(content))
        return json.loads(repaired_content)
        
    except Exception as e:
        logger.error(f"Erro no Planner: {e}. Raw: {str(content)[:100]}")
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
