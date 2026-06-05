#!/usr/bin/env python3
"""
brain/scheduler.py — Camada 2: Scheduler (Llama 70B ou 8B - Groq)
Responsável por analisar o plano e escolher as ferramentas necessárias.
Objetivo: Reduzir drasticamente o uso de tokens.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from brain.llm import get_llm, GROQ_MODELS

logger = logging.getLogger("luna.scheduler")

COMPACT_TOOLS_LIST = """
Busca e Web:
- search_web: pesquisa geral na internet
- read_webpage: extrai texto de uma URL
- click_web_result: clica em resultado de busca
- open_url: abre uma URL diretamente

Navegação e Desktop:
- see_screen: analisa o que está na tela (OCR/Vision)
- click_on_screen: clica em elemento na tela
- open_app: abre um aplicativo pelo nome
- desktop_type: digita texto na tela
- desktop_hotkey: pressiona atalhos de teclado (ex: ctrl+c)
- control_window: maximiza, minimiza ou fecha janelas
- focus_window: traz uma janela para o primeiro plano
- list_windows: lista janelas abertas

Sistema e Arquivos:
- run_bash_command: executa comando shell (linux)
- run_terminal_command: abre terminal e executa comando
- filesystem: operações de arquivo (copy, move, delete, list)
- read_file: lê conteúdo de arquivo texto
- save_file: salva texto em arquivo
- get_system_status: cpu, ram, bateria
- kill_process: encerra um processo/app

Google Services:
- google_query: busca rápida no Calendar/Gmail
- google_send_email: envia e-mail
- google_create_event: cria evento na agenda
- google_search_emails: busca e-mails específicos
- google_read_email: lê conteúdo de um e-mail
- google_drive_list: lista arquivos no Drive
- google_drive_upload: envia arquivo para o Drive

Produtividade e Casa:
- control_spotify: play, pause, next, toca música/playlist
- control_lights: controla lâmpadas inteligentes
- get_weather: previsão do tempo
- set_timer: define despertador/timer
- manage_reminder: cria/lista lembretes
- manage_notes: gerencia notas pessoais
- manage_shopping_list: lista de compras
- manage_focus: modo pomodoro/foco
- get_daily_briefing: resumo do dia
- whatsapp_action: envia mensagem ou abre chat

Utilidades e Outros:
- trigger_n8n_workflow: aciona automações complexas (e-mail, Discord, WhatsApp, navegação web avançada) no n8n via webhook. Use 'path': 'luna-gateway' e 'data': {'service': 'gmail|discord|whatsapp|web', ...}
- create_excel: gera planilha Excel
- create_pdf_drive: gera PDF no Drive
- clipboard_action: copia ou cola do clipboard
- search_memory: busca fatos na memória de longo prazo da Luna
- crew_run: executa agente especializado (CrewAI)
"""

SCHEDULER_PROMPT = """Você é o Scheduler da Luna. Sua função é escolher APENAS as ferramentas necessárias para executar o PLANO ESTRATÉGICO fornecido.

Você deve retornar APENAS um JSON válido seguindo este formato:

{
  "reasoning": "Sua lógica para escolher estas ferramentas",
  "tools_to_call": [
    {
      "tool_name": "nome_da_ferramenta",
      "parameters": {
        "param1": "valor1"
      },
      "explanation": "Por que esta ferramenta é necessária agora"
    }
  ],
  "execution_mode": "sequential|parallel",
  "confidence": 0.0 a 1.0,
  "fallback": "O que fazer se as ferramentas falharem"
}

REGRAS:
1. Responda APENAS o JSON.
2. Escolha o MENOR número possível de ferramentas para cumprir o plano.
3. Se o plano não exigir ferramentas (apenas conversa), retorne "tools_to_call": [].
4. Certifique-se de que os nomes das ferramentas existam na LISTA DE FERRAMENTAS abaixo.

LISTA DE FERRAMENTAS DISPONÍVEIS:
""" + COMPACT_TOOLS_LIST

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
    try:
        json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("\n", " ").replace("\r", " ")
        if text.count('"') % 2 != 0:
             text += '"'
    return text

def select_tools(plan_json: Dict[str, Any], user_input: str, context: str = "") -> Dict[str, Any]:
    """
    Analisa o plano e seleciona as ferramentas usando Llama 70B ou 8B.
    """
    llm = get_llm()
    plan_text = json.dumps(plan_json, indent=2, ensure_ascii=False)
    
    messages = [
        {"role": "system", "content": SCHEDULER_PROMPT},
        {"role": "user", "content": f"Pedido do Usuário: {user_input}\n\nPlano Estratégico:\n{plan_text}\n\nResponda APENAS o JSON puro:"}
    ]
    
    model = GROQ_MODELS.get("heavy", "llama-3.3-70b-versatile")
    
    try:
        raw_response = llm.generate(messages=messages, task_type="planning", model=model)
        content = raw_response.get("message", {}).get("content", "") if isinstance(raw_response, dict) else raw_response
        
        repaired_content = _repair_json(content)
        scheduler_json = json.loads(repaired_content)
        logger.info(f"Ferramentas selecionadas: {[t['tool_name'] for t in scheduler_json.get('tools_to_call', [])]}")
        return scheduler_json
        
    except Exception as e:
        logger.error(f"Erro no Scheduler: {e}. Raw: {content[:100]}")
        return {
            "reasoning": "Erro ao processar Scheduler.",
            "tools_to_call": [],
            "execution_mode": "sequential",
            "confidence": 0.0,
            "fallback": "Conversar com o usuário sobre o erro."
        }
