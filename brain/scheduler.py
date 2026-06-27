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
- desktop_hotkey: pressiona atalhos de teclado
- control_window: maximiza, minimiza ou fecha janelas
- focus_window: traz uma janela para o primeiro plano
- list_windows: lista janelas abertas

Sistema e Arquivos:
- system_control: ação bash (ls, mkdir, etc.), terminal, status, kill, notification, brightness, network, screenshot.
- filesystem: list (listar), read (ler), write (editar/ESCREVER), mkdir, move, delete, stat, search. ⚠️ write SEMPRE pede confirmação ao usuário antes de executar.
- run_browser_task: automação web complexa (browser-use).

Google Services:
- google_services: query (calendar/gmail), search_emails, read_email, events_by_date.
- google_calendar_manage: create, edit, delete eventos.
- google_gmail_manage: send, reply, forward, mark_read, delete e-mails.
- google_drive_manage: upload, list, search, create_folder, delete arquivos no Drive.

Produtividade e Casa:
- control_spotify: play, pause, next, toca música.
- control_lights: on/off lâmpadas.
- get_weather: clima.
- set_timer: despertador/timer.
- manage_reminder: add, list, cancel lembretes.
- manage_notes: add, list, search, delete notas.
- manage_shopping_list: add, remove, list, clear compras.

Projetos:
- check_project: verifica estado REAL de um projeto/pasta — lista arquivos, lê conteúdo. NUNCA invente — use isto para checar.
- write_code: escreve arquivo de código em QUALQUER caminho (absoluto ou relativo).
- create_project: cria pasta de projeto com múltiplos arquivos em QUALQUER lugar.
- manage_focus: start, break, cancel, status pomodoro.
- get_daily_briefing: resumo do dia.
- whatsapp_action: open, send, status whatsapp.

Utilidades e Outros:
- agno_run: executa agente Agno especializado.
- crew_run: executa enxame CrewAI especializado.
- write_code: CRIA ou SOBRESCREVE um arquivo de código em Luna-programming. Params: filename, content.
- create_project: CRIA projeto COMPLETO em Luna-programming. Params: project_name, files[{filename, content}].
- document_services: create_excel, create_pdf, read_file, save_file.
- clipboard_action: read, write clipboard.
- search_memory: busca na memória da Luna.
- save_skill: salva sequência de passos como habilidade.
"""

SCHEDULER_PROMPT = """Você é o Scheduler da Luna. Sua função é escolher APENAS as ferramentas necessárias para executar o PLANO ESTRATÉGICO fornecido.

REGRAS DE PARÂMETROS:
- LIMPEZA: Nunca inclua pontuação desnecessária (como '?' ou '.') no final de caminhos de arquivos ou nomes de pastas.
- CAMINHOS: Se o usuário pedir "minha home", use "~". Se pedir uma pasta X, use "~/X".
- STRINGS: Forneça parâmetros limpos e prontos para execução bash/python.

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

LISTA DE FERRAMENTAS DISPONÍVEIS:
""" + COMPACT_TOOLS_LIST

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
        m = re.search(r'(\[.*\])', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            return "{}"

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
    
    content = ""
    try:
        raw_response = llm.generate(messages=messages, task_type="planning", model=model)
        content = raw_response.get("message", {}).get("content", "") if isinstance(raw_response, dict) else (raw_response or "")
        
        repaired_content = _repair_json(str(content))
        scheduler_json = json.loads(repaired_content)
        tools = scheduler_json.get("tools_to_call", [])
        logger.info(f"Ferramentas selecionadas: {[t['tool_name'] for t in tools]}")
        return scheduler_json
        
    except Exception as e:
        logger.error(f"Erro no Scheduler: {e}. Raw: {str(content)[:100]}")
        # Fallback: tenta inferir ferramentas por keyword matching
        tools = _fallback_tools(user_input)
        return {
            "reasoning": f"Fallback por keyword. Erro original: {e}",
            "tools_to_call": tools,
            "execution_mode": "sequential",
            "confidence": 0.5,
            "fallback": tools[0]["tool_name"] if tools else "Conversar com o usuário sobre o erro."
        }


def _fallback_tools(user_input: str) -> list:
    """Fallback baseado em keywords quando o scheduler falha."""
    tl = user_input.lower()
    
    # Mapeamento keyword → (tool_name, params)
    rules = [
        (["pasta", "pastas", "arquivo", "arquivos", "home", "diretório", "diretorio", "lista", "listar"],
         {"tool_name": "filesystem", "parameters": {"action": "list", "path": "~"}}),
        (["luz", "lâmpada", "lampada", "iluminação", "sala"],
         {"tool_name": "control_lights", "parameters": {"state": "off" if any(w in tl for w in ["apaga", "desliga", "desligar", "apagar"]) else "on"}}),
        (["processo", "processador", "cpu", "memória", "memoria", "ram", "desempenho", "performance", "status do pc"],
         {"tool_name": "system_control", "parameters": {"action": "status"}}),
        (["tempo", "clima", "chuva", "temperatura", "chove", "previsão", "previsao"],
         {"tool_name": "get_weather", "parameters": {}}),
        (["timer", "cronometro", "cronômetro", "segundos", "minutos", "despertador"],
         {"tool_name": "set_timer", "parameters": {}}),
        (["nota", "anota", "bloco", "anotação", "anotacao"],
         {"tool_name": "manage_notes", "parameters": {}}),
        (["lembra", "lembrete", "avisa", "avisar"],
         {"tool_name": "manage_reminder", "parameters": {}}),
        (["spotify", "toca", "tocar", "musica", "música", "playlist"],
         {"tool_name": "control_spotify", "parameters": {}}),
        (["abre", "abrir", "inicia", "iniciar", "firefox", "chrome", "terminal", "navegador"],
         {"tool_name": "open_app", "parameters": {"app_name": ""}}),
        (["lê", "ler", "leia", "mostra", "exibe", "abrir arquivo", "conteúdo"],
         {"tool_name": "filesystem", "parameters": {"action": "read", "path": "~"}}),
        (["edita", "editar", "modifica", "modificar", "altera", "alterar", "muda", "mudar", "substitui", "reescreve"],
         {"tool_name": "filesystem", "parameters": {"action": "write", "path": "", "content": ""}}),
        (["cria", "criar", "escreve", "escrever", "codigo", "código", "arquivo", "script", "programa", "app", "site", "pagina", "página"],
         {"tool_name": "write_code", "parameters": {"filename": "", "content": ""}}),
        (["projeto", "project", "sistema completo", "aplicação", "aplicacao", "cria um", "faz um", "crie um", "desenvolve"],
         {"tool_name": "create_project", "parameters": {"project_name": "", "files": []}}),
        (["pesquisa", "pesquisar", "busca", "buscar", "google", "pesquise", "procura"],
         {"tool_name": "search_web", "parameters": {}}),
        (["checa", "checar", "verifica", "verificar", "estado do projeto", "como está o", "status do"],
         {"tool_name": "check_project", "parameters": {"path": "auto", "deep": False}}),
        (["briefing", "resumo do dia", "hoje", "dia"],
         {"tool_name": "get_daily_briefing", "parameters": {}}),
        (["tela", "print", "screenshot", "captura"],
         {"tool_name": "system_control", "parameters": {"action": "screenshot"}}),
    ]
    
    for keywords, tool in rules:
        if any(kw in tl for kw in keywords):
            # Extrai nome do app se for open_app
            if tool["tool_name"] == "open_app":
                for app in ["firefox", "chrome", "terminal", "spotify", "whatsapp", "discord", "vscode", "code"]:
                    if app in tl:
                        tool["parameters"]["app_name"] = app
                        break
                if not tool["parameters"]["app_name"]:
                    tool["parameters"]["app_name"] = tl.split("abre")[-1].split("abrir")[-1].strip() or tl.split("inicia")[-1].split("iniciar")[-1].strip()
            # Extrai nome do projeto para check_project
            if tool["tool_name"] == "check_project" and tool["parameters"].get("path") == "auto":
                import re as _re
                # Tenta extrair nome após "projeto" ou "fogos" ou palavras-chave
                m = _re.search(r'(?:projeto|fogos|pasta|dire[tto][óo]rio)\s+["""]?([\w\-\./]+)["""]?', tl)
                if m:
                    tool["parameters"]["path"] = m.group(1)
                else:
                    # Pega a última palavra da query como nome do projeto
                    words = [w for w in tl.split() if len(w) > 2 and w not in ("checa", "checar", "verifica", "verificar", "estado", "como", "está", "o", "da", "do", "de")]
                    tool["parameters"]["path"] = words[-1] if words else "."
                tool["parameters"]["deep"] = True
            return [tool]
    
    return []
