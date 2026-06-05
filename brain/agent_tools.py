#!/usr/bin/env python3
import json
import re
import logging
import time

logger = logging.getLogger("luna.agent_tools")

from actions.google_services import get_google


LUNA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "trigger_n8n_workflow",
            "description": "Aciona automações no n8n. Use 'path': 'luna-gateway' para e-mail, discord, whatsapp e web. No 'data', envie 'service' e os campos necessários (to, subject, text, webhook_url, url).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho do webhook no n8n."},
                    "data": {"type": "object", "description": "Dados JSON para o workflow."}
                },
                "required": ["path", "data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_services",
            "description": "Acesso direto ao Google Calendar e Gmail (leitura/busca).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["query", "search_emails", "read_email", "events_by_date"]},
                    "service": {"type": "string", "enum": ["calendar", "gmail"]},
                    "query": {"type": "string", "description": "Termo de busca ou ID."},
                    "date": {"type": "string", "description": "Data YYYY-MM-DD."},
                    "max_results": {"type": "integer", "default": 5}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_manage",
            "description": "Cria, edita ou deleta eventos no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "edit", "delete"]},
                    "event_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 8601"},
                    "end_time": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_gmail_manage",
            "description": "Envia, responde, encaminha ou marca e-mails no Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["send", "reply", "forward", "mark_read", "delete"]},
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "message_id": {"type": "string"},
                    "extra_text": {"type": "string"},
                    "attachments": {"type": "string", "description": "Nomes de arquivos separados por vírgula."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_manage",
            "description": "Gerencia arquivos no Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["upload", "list", "search", "create_folder", "delete"]},
                    "filepath": {"type": "string"},
                    "query": {"type": "string"},
                    "folder_name": {"type": "string"},
                    "file_id": {"type": "string"},
                    "parent_id": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crew_run",
            "description": "Execute a high‑level CrewAI task description and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Descrição completa da tarefa que a Crew deve executar."
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "document_services",
            "description": "Cria ou lê arquivos (Excel, PDF, TXT, CSV).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create_excel", "create_pdf", "read_file", "save_file"]},
                    "data": {"type": "array", "items": {"type": "object"}},
                    "content": {"type": "string"},
                    "filename": {"type": "string"},
                    "filepath": {"type": "string"},
                    "title": {"type": "string"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_tools",
            "description": "Controle e status do hardware/sistema (CPU, RAM, processos, terminal, brilho, rede, print).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["status", "processes", "bash", "terminal", "kill", "notification", "brightness", "network", "screenshot"]},
                    "command": {"type": "string"},
                    "visible": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 10},
                    "pid": {"type": "integer"},
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "level": {"type": "integer"},
                    "path": {"type": "string"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Consulta clima e previsão do tempo. Use para perguntas sobre tempo, temperatura ou chuva.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Cidade opcional (ex: 'São Paulo'). Vazio = localização automática."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Cria, consulta ou cancela timers de contagem regressiva.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "status", "cancel"],
                        "description": "start=iniciar, status=ver ativos, cancel=cancelar todos."
                    },
                    "minutes": {"type": "integer", "description": "Minutos (para action=start)."},
                    "seconds": {"type": "integer", "description": "Segundos extras (para action=start)."},
                    "name": {"type": "string", "description": "Nome do timer (ex: 'macarrão')."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_reminder",
            "description": "Gerencia lembretes com horário. Use para 'me lembra de... às 20h'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "list", "cancel"]},
                    "message": {"type": "string", "description": "Texto do lembrete."},
                    "when": {"type": "string", "description": "Quando lembrar em linguagem natural (ex: 'às 20h', 'em 2 horas', 'amanhã às 9h')."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_notes",
            "description": "Anotações rápidas persistentes: criar, listar, buscar ou apagar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "list", "search", "delete"]},
                    "content": {"type": "string", "description": "Texto da nota (add)."},
                    "query": {"type": "string", "description": "Termo de busca (search)."},
                    "index": {"type": "integer", "description": "Número da nota (delete)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_shopping_list",
            "description": "Lista de compras: adicionar, remover, listar ou limpar itens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "remove", "list", "clear"]},
                    "item": {"type": "string", "description": "Item da lista (add/remove)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_focus",
            "description": "Modo foco / Pomodoro: iniciar sessão, cancelar ou ver status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "break", "cancel", "status"]},
                    "minutes": {"type": "integer", "description": "Duração em minutos (start/break). Padrão: 25."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_briefing",
            "description": (
                "Briefing do dia: clima (SP + Itapecerica), lembretes de hoje, notas recentes "
                "e resumo natural. Use para 'o que temos pra hoje', 'briefing', 'resumo do dia'."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_browser_task",
            "description": (
                "Automatiza tarefa complexa no navegador (browser-use): navegar, pesquisar, "
                "preencher formulários. Use quando open_url/search_web/click_web_result não bastarem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Tarefa em linguagem natural ou URL inicial."
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Salva captura de tela em arquivo e retorna o caminho.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho opcional do arquivo PNG."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_window",
            "description": "Controla janelas do desktop: fechar, minimizar, maximizar ou trocar workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["close", "minimize", "maximize", "fullscreen", "workspace"],
                    },
                    "workspace": {"type": "integer", "description": "Número do workspace (1-10) quando action=workspace."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_action",
            "description": "Lê ou escreve na área de transferência do sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write"]},
                    "text": {"type": "string", "description": "Texto para copiar (write)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "see_screen",
            "description": "Captura e descreve o que está na tela do usuário (OCR + contexto visual).",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "Opcional: o que procurar na tela (ex: 'botão enviar', 'primeiro link')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Abre uma URL no navegador padrão.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa ou domínio (ex: youtube.com)."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Pesquisa na web via Google e abre no navegador. "
                "Use para 'pesquisa/busca/procura [X]'. NÃO use click_on_screen para pesquisar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de pesquisa."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Lê e extrai o conteúdo textual de uma página web (URL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL da página."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_spotify",
            "description": "Controla música no Spotify: tocar, pausar, pular, volume ou buscar artista/música.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "prev", "status", "volume", "search"],
                    },
                    "query": {"type": "string", "description": "Música/artista (search) ou nível 0-100 (volume)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_lights",
            "description": "Liga ou desliga a luz física da sala.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "enum": ["on", "off"]}
                },
                "required": ["state"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Busca fatos salvos sobre o usuário e conversas anteriores na memória da Luna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "O que lembrar/buscar."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_on_screen",
            "description": (
                "Clica em botão ou texto visível em apps/janelas locais (OCR). "
                "NÃO use para resultados do Google — use click_web_result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Texto ou descrição do elemento."}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_web_result",
            "description": (
                "Abre ou clica no N-ésimo resultado de uma pesquisa web (Google). "
                "Use para 'clica no primeiro resultado', 'abre o segundo link da busca'. "
                "Preferir sobre click_on_screen. index=0 é o primeiro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "0=primeiro, 1=segundo resultado. Padrão 0.",
                        "default": 0,
                    },
                    "query": {
                        "type": "string",
                        "description": "Termo buscado (opcional; usa última pesquisa se vazio).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Abre aplicativo instalado pelo nome (firefox, spotify, terminal, vscode, discord). "
                "Use para 'abre/abrir/inicia [app]'. NUNCA use click_on_screen para abrir apps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Nome do app (ex: firefox, spotify, terminal)."}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filesystem",
            "description": (
                "Gerencia arquivos e pastas do PC (home do usuário). "
                "Ações: list, read, write, mkdir, move, delete, stat, search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "read", "write", "mkdir", "move", "delete", "stat", "search"],
                    },
                    "path": {"type": "string", "description": "Caminho (~, ~/Documents, etc.)"},
                    "content": {"type": "string", "description": "Conteúdo (write)."},
                    "destination": {"type": "string", "description": "Destino (move)."},
                    "query": {"type": "string", "description": "Busca por nome (search)."},
                    "pattern": {"type": "string", "description": "Glob para list (ex: *.py)."},
                    "append": {"type": "boolean", "description": "Anexar ao arquivo (write)."},
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_type",
            "description": "Digita texto no app/janela focada (como se você estivesse digitando).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Texto a digitar."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_hotkey",
            "description": "Pressiona tecla ou atalho (enter, ctrl+c, alt+Tab, super, f11, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Atalho (ex: 'ctrl+s', 'alt+Tab', 'Return')."}
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "Lista janelas abertas no desktop.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Foca/traz para frente uma janela pelo título parcial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Parte do título (ex: 'Firefox', 'WhatsApp')."}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Controla qualquer player de mídia (Spotify, VLC, browser) via playerctl — sem API key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "prev", "stop", "status", "volume_up", "volume_down", "volume", "mute"],
                    },
                    "level": {"type": "integer", "description": "Volume 0-100 (action=volume)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": (
                "Encerra/mata processo por nome ou PID. "
                "Use para 'mata/fecha/encerra firefox', 'para o spotify'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "name": {"type": "string", "description": "Nome do processo (ex: firefox)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Envia notificação desktop ao usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["title", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_control",
            "description": "Controles de hardware/rede locais: brilho, rede, screenshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["brightness", "network", "screenshot"],
                    },
                    "level": {"type": "integer", "description": "Brilho 1-100."},
                    "path": {"type": "string", "description": "Caminho do screenshot."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "whatsapp_action",
            "description": (
                "WhatsApp sem API key: abrir app ou enviar mensagem via automação de tela. "
                "Opcional: WHATSAPP_BRIDGE_URL no .env para bridge local."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "send", "status"]},
                    "contact": {"type": "string", "description": "Nome ou número (send)."},
                    "message": {"type": "string", "description": "Texto da mensagem (send)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_home_info",
            "description": "Salva uma informação sobre a casa do usuário (senha do wifi, onde ficam as chaves, rotinas domésticas, receitas, etc.) na memória de longo prazo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "A informação a ser salva (ex: 'A senha do wifi é Luna2026')."
                    },
                    "category": {
                        "type": "string",
                        "description": "Categoria opcional (ex: 'wifi', 'receita', 'rotina', 'geral').",
                        "default": "geral"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_home_info",
            "description": "Busca informações salvas sobre a casa do usuário na memória de longo prazo (wifi, chaves, receitas, rotinas, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca (ex: 'senha wifi', 'receita de bolo')."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Substrings proibidas — o LLM pode alucinar comandos destrutivos
_CMD_BLOCKLIST = [
    "rm -rf", "rm -r", "sudo rm", "mkfs", "dd if=",
    "shutdown", "reboot", "halt", "poweroff",
    ":(){:|:&};:", "chmod 777 /", "chown -R",
    "curl | sh", "wget | sh", "bash <(",
]

# Palavras que indicam controle de playback (não são buscas)
_SPOTIFY_CONTROLS = {
    "next": "next", "próxima": "next", "proxima": "next", "pular": "next", "avançar": "next",
    "prev": "prev", "anterior": "prev", "voltar": "prev",
    "pause": "pause", "pausar": "pause", "parar": "pause", "para": "pause",
    "play": "play", "tocar": "play", "retomar": "play", "continuar": "play",
    "stop": "stop",
    "status": "status", "o que toca": "status", "que música": "status",
    "volume": "volume",
}


def _format_result(result: str) -> str:
    """Padroniza retorno para o loop do agente (SUCESSO:/FALHOU:)."""
    text = str(result).strip()
    if not text:
        return "FALHOU: Resultado vazio."
    upper = text.upper()
    if upper.startswith("SUCESSO:") or upper.startswith("FALHOU:"):
        return text
    if upper.startswith("FALHOU") or text.lower().startswith("erro"):
        return text if upper.startswith("FALHOU") else f"FALHOU: {text}"
    return f"SUCESSO: {text}"


def is_tool_success(result: str) -> bool:
    return not str(result).strip().upper().startswith("FALHOU")


def tool_call_id(tool_call) -> str:
    if isinstance(tool_call, dict):
        return tool_call.get("id") or f"call_{int(time.time() * 1000)}"
    return getattr(tool_call, "id", None) or f"call_{int(time.time() * 1000)}"


def tool_call_name(tool_call) -> str:
    if isinstance(tool_call, dict):
        return tool_call.get("function", {}).get("name", "")
    return getattr(tool_call.function, "name", "")


def tool_call_args(tool_call) -> dict:
    if isinstance(tool_call, dict):
        raw = tool_call.get("function", {}).get("arguments", {})
    else:
        raw = tool_call.function.arguments
    return _parse_arguments(raw)


def tool_call_signature(tool_call) -> str:
    name = tool_call_name(tool_call)
    args = tool_call_args(tool_call)
    return f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def _is_blocked(cmd: str) -> bool:
    """Retorna True se o comando contém substring perigosa."""
    cmd_lower = cmd.lower()
    return any(bad in cmd_lower for bad in _CMD_BLOCKLIST)


def _parse_arguments(raw_arguments) -> dict:
    """
    Parseia argumentos do tool_call de forma robusta.
    Aceita str (JSON), dict, ou tenta extração via regex como fallback.
    """
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not raw_arguments:
        return {}
    try:
        parsed = json.loads(raw_arguments)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except (json.JSONDecodeError, TypeError):
        # Fallback: extrai o valor de "command" via regex
        m = re.search(r'"command"\s*:\s*"([^"]+)"', str(raw_arguments))
        if m:
            return {"command": m.group(1)}
        logger.warning("Não foi possível parsear argumentos: %s", raw_arguments)
        return {}


def _handle_spotify(executor, query: str) -> str:
    """Roteador inteligente do Spotify: separa controles de buscas."""
    query_lower = query.lower().strip()

    for kw, action in _SPOTIFY_CONTROLS.items():
        if query_lower == kw or query_lower.startswith(kw + " "):
            try:
                sp = executor.spotify
                if action == "next":
                    return sp.next_track()
                elif action == "prev":
                    return sp.prev_track()
                elif action in ("pause", "stop"):
                    return sp.pause()
                elif action == "play":
                    return sp.play()
                elif action == "status":
                    return sp.now_playing()
                elif action == "volume":
                    parts = query_lower.split()
                    for p in parts:
                        if p.isdigit():
                            return sp.set_volume(int(p))
                    return sp.set_volume(70)
            except Exception as e:
                return f"[Spotify] Erro no controle: {e}"

    try:
        res = executor.spotify.handle(f"toca {query}")
        return str(res)
    except Exception as e:
        return f"[Spotify] Erro na busca: {e}"


def execute_tool_call(executor, tool_call) -> str:
    """Executa o comando interno enviado pelo LLM. Retorna resultado imediatamente."""
    try:
        # Suporta tanto NormalizedToolCall (dataclass) quanto dict
        if isinstance(tool_call, dict):
            name = tool_call.get("function", {}).get("name", "")
            raw_args = tool_call.get("function", {}).get("arguments", {})
        else:
            name = tool_call.function.name
            raw_args = tool_call.function.arguments

        if name == "trigger_n8n_workflow":
            args = _parse_arguments(raw_args)
            path = args.get("path")
            data = args.get("data", {})
            if not path:
                return "FALHOU: 'path' é obrigatório para acionar o n8n."
            
            import requests
            n8n_url = f"http://localhost:5678/webhook/{path}"
            try:
                print(f"[n8n] Acionando workflow: {path}...")
                resp = requests.post(n8n_url, json=data, timeout=10)
                if resp.status_code < 300:
                    return f"SUCESSO: Workflow '{path}' acionado no n8n. Resposta: {resp.text[:200]}"
                else:
                    return f"FALHOU: n8n retornou erro {resp.status_code}: {resp.text}"
            except Exception as e:
                return f"FALHOU: Erro ao conectar com n8n: {e}"

        elif name == "google_services":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            gm = get_google()
            if action == "query":
                service = args.get("service")
                max_results = args.get("max_results", 5)
                if service == "calendar":
                    return gm.get_calendar_events(max_results)
                elif service == "gmail":
                    return gm.get_unread_emails(max_results)
                return f"FALHOU: Serviço desconhecido '{service}'."
            elif action == "search_emails":
                return gm.search_emails(args.get("query"), args.get("max_results", 5))
            elif action == "read_email":
                return gm.read_email(args.get("query")) # query as message_id
            elif action == "events_by_date":
                return gm.get_events_by_date(args.get("date"), args.get("max_results", 20))
            return f"FALHOU: Ação '{action}' desconhecida para google_services."

        elif name == "google_calendar_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            gm = get_google()
            if action == "create":
                return gm.create_calendar_event(
                    args.get("summary"), args.get("start_time"), args.get("end_time"),
                    args.get("description"), args.get("location"), args.get("attendees", "")
                )
            elif action == "edit":
                return gm.edit_calendar_event(
                    args.get("event_id"), args.get("summary"), args.get("start_time"),
                    args.get("end_time"), args.get("description"), args.get("location")
                )
            elif action == "delete":
                return gm.delete_calendar_event(args.get("event_id"))
            return f"FALHOU: Ação '{action}' desconhecida para google_calendar_manage."

        elif name == "google_gmail_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            gm = get_google()
            if action == "send":
                return gm.send_email(args.get("to"), args.get("subject"), args.get("body"), args.get("attachments", ""))
            elif action == "reply":
                return gm.reply_email(args.get("message_id"), args.get("body"))
            elif action == "forward":
                return gm.forward_email(args.get("message_id"), args.get("to"), args.get("extra_text", ""))
            elif action == "mark_read":
                return gm.mark_as_read(args.get("message_id"))
            elif action == "delete":
                return gm.delete_email(args.get("message_id"))
            return f"FALHOU: Ação '{action}' desconhecida para google_gmail_manage."

        elif name == "google_drive_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            gm = get_google()
            if action == "upload":
                return gm.google_drive_upload(args.get("filepath_or_name"), args.get("folder_id"))
            elif action == "list":
                return gm.google_drive_list(args.get("max_results", 10))
            elif action == "search":
                return gm.google_drive_search(args.get("query"), args.get("max_results", 10))
            elif action == "create_folder":
                return gm.google_drive_create_folder(args.get("folder_name"), args.get("parent_id"))
            elif action == "delete":
                return gm.google_drive_delete(args.get("file_id"))
            return f"FALHOU: Ação '{action}' desconhecida para google_drive_manage."
        elif name == "document_services":
            from actions.document_services import get_doc_services
            args = _parse_arguments(raw_args)
            action = args.get("action")
            ds = get_doc_services()
            if action == "create_excel":
                return ds.create_excel(args.get("data"), args.get("filename"))
            elif action == "create_pdf":
                return ds.create_pdf_drive(args.get("content"), args.get("title"))
            elif action == "read_file":
                return ds.read_file(args.get("filepath_or_name"))
            elif action == "save_file":
                return ds.save_file(args.get("content"), args.get("filepath_or_name"))
            return f"FALHOU: Ação '{action}' desconhecida para document_services."

        elif name == "system_tools":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            action = args.get("action")
            st = get_system_tools()
            if action == "status":
                return str(st.get_system_status())
            elif action == "processes":
                return st.get_running_processes(args.get("limit", 10))
            elif action == "bash":
                return st.run_bash_command(args.get("command"), visible=args.get("visible", False))
            elif action == "terminal":
                return st.run_terminal_command(args.get("command"))
            elif action == "kill":
                return st.kill_process(args.get("pid", 0), args.get("name", ""))
            elif action == "notification":
                return st.send_notification(args.get("title", "Luna"), args.get("message", ""))
            elif action == "brightness":
                return st.set_brightness(args.get("level", 50))
            elif action == "network":
                return st.get_network_status()
            elif action == "screenshot":
                return st.take_screenshot(args.get("path"))
            return f"FALHOU: Ação '{action}' desconhecida para system_tools."
        elif name == "save_home_info":
            from brain.memory import get_memory
            args = _parse_arguments(raw_args)
            text = args.get("text")
            if not text:
                return "FALHOU: text é obrigatório."
            rag = get_memory().rag
            if rag:
                return rag.remember_home_info(text, args.get("category", "geral"))
            return "FALHOU: RAG não está disponível."
        elif name == "search_home_info":
            from brain.memory import get_memory
            args = _parse_arguments(raw_args)
            query = args.get("query")
            if not query:
                return "FALHOU: query é obrigatória."
            rag = get_memory().rag
            if rag:
                result = rag.retrieve_home_info(query)
                return result if result else "Nenhuma informação encontrada sobre a casa para essa busca."
            return "FALHOU: RAG não está disponível."
        elif name == "crew_run":
            from brain.crew import run_crew_task
            args = _parse_arguments(raw_args)
            task_desc = args.get("task_description", "")
            if not task_desc:
                return _format_result("FALHOU: crew_run requires a task_description.")
            return _format_result(run_crew_task(task_desc))
        elif name == "get_weather":
            from actions.weather import get_weather
            args = _parse_arguments(raw_args)
            return _format_result(get_weather().get_weather(args.get("city", "")))
        elif name == "set_timer":
            args = _parse_arguments(raw_args)
            action = args.get("action", "start")
            if action == "status":
                return _format_result(executor.timer.status())
            if action == "cancel":
                for n in list(executor.timer.timers.keys()):
                    executor.timer.cancel_timer(n)
                return _format_result("Todos os timers foram cancelados.")
            minutes = int(args.get("minutes") or 0)
            seconds = int(args.get("seconds") or 0)
            if minutes <= 0 and seconds <= 0:
                return _format_result("FALHOU: Informe minutes ou seconds para iniciar o timer.")
            name = args.get("name") or "Padrão"
            executor.timer.add_timer(minutes * 60 + seconds, name)
            return _format_result(f"Timer de {minutes}m {seconds}s iniciado: {name}.")
        elif name == "productivity_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            if action == "focus":
                act = args.get("sub_action", "status")
                if act == "start": return _format_result(executor.focus.start_focus(args.get("minutes", 25)))
                if act == "break": return _format_result(executor.focus.start_break(args.get("minutes", 5)))
                if act == "cancel": return _format_result(executor.focus.cancel())
                return _format_result(executor.focus.status())
            elif action == "reminder":
                act = args.get("sub_action", "list")
                if act == "list": return _format_result(executor.reminders.list_reminders())
                if act == "cancel": return _format_result(executor.reminders.cancel(args.get("message", "")))
                return _format_result(executor.reminders.add(args.get("message", ""), executor.reminders.parse_datetime(args.get("when", ""))))
            elif action == "notes":
                act = args.get("sub_action", "list")
                if act == "add": return _format_result(executor.notes.add(args.get("content", "")))
                if act == "list": return _format_result(executor.notes.list_notes())
                if act == "search": return _format_result(executor.notes.search(args.get("query", "")))
                if act == "delete": return _format_result(executor.notes.delete(int(args.get("index", 0))))
            elif action == "shopping":
                act = args.get("sub_action", "list")
                if act == "list": return _format_result(executor.shopping.format_list())
                if act == "clear": return _format_result(executor.shopping.handle("limpa a lista"))
                if act in ["add", "remove"]: return _format_result(executor.shopping.handle(f"{'adiciona' if act=='add' else 'remove'} {args.get('item', )}"))
            return f"FALHOU: Ação '{action}' desconhecida para productivity_manage."

        elif name == "desktop_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            if action == "window":
                sub = args.get("sub_action")
                if sub == "close": return _format_result(executor.wm.close_active())
                if sub == "minimize": return _format_result(executor.wm.minimize_active())
                if sub == "maximize": return _format_result(executor.wm.maximize_active())
                if sub == "workspace": return _format_result(executor.wm.go_to_workspace(int(args.get("workspace", 1))))
            elif action == "type": return _format_result(executor.type_text(args.get("text", "")).get("message", "OK"))
            elif action == "hotkey": return _format_result(executor.press_key(args.get("keys", "")).get("message", "OK"))
            elif action == "clipboard":
                if args.get("sub_action") == "write": return _format_result(executor.clipboard.write(args.get("text", "")))
                return _format_result(executor.clipboard.get_current())
            elif action == "list_windows": return _format_result(executor.wm.list_windows())
            elif action == "focus_window": return _format_result(executor.wm.focus_window(args.get("title", "")))
            return f"FALHOU: Ação '{action}' desconhecida para desktop_manage."

        elif name == "media_manage":
            args = _parse_arguments(raw_args)
            action = args.get("action")
            if action == "spotify":
                return _format_result(_handle_spotify(executor, args.get("query", "")))
            elif action == "player":
                from actions.media import get_media
                m = get_media()
                sub = args.get("sub_action")
                if sub == "volume": return _format_result(m.set_volume(int(args.get("level", 50))))
                actions = {"play": m.play, "pause": m.pause, "next": m.next_track, "prev": m.prev_track, "status": m.get_status}
                return _format_result(actions[sub]() if sub in actions else "FALHOU: ação inválida.")
            return f"FALHOU: Ação '{action}' desconhecida para media_manage."
        elif name == "control_lights":
            args = _parse_arguments(raw_args)
            state = args.get("state", "").lower()
            if state not in ("on", "off"):
                return _format_result("FALHOU: state deve ser 'on' ou 'off'.")
            action = "acender luzes" if state == "on" else "apagar luzes"
            res = executor.lights.handle(action)
            return _format_result(res or "Luzes atualizadas.")
        elif name == "search_memory":
            from brain.memory import get_memory
            args = _parse_arguments(raw_args)
            query = args.get("query", "").strip()
            if not query:
                return _format_result("FALHOU: query é obrigatória.")
            ctx = get_memory().get_context_for_prompt(query)
            return _format_result(ctx or "Nenhuma memória relevante encontrada.")
        elif name == "click_on_screen":
            args = _parse_arguments(raw_args)
            target = args.get("target", "").strip()
            if not target:
                return _format_result("FALHOU: target é obrigatório.")
            from actions.web_nav import try_click_web_result, is_web_result_click
            if is_web_result_click(target):
                web_res = try_click_web_result(
                    target,
                    executor,
                    search_query=getattr(executor.web_manager, "last_search_query", ""),
                )
                if web_res and web_res.get("success"):
                    return _format_result(web_res.get("message", "OK"))
            from actions.executor import _resolve_click
            import unicodedata as _ud
            norm = "".join(
                c for c in _ud.normalize("NFD", target)
                if _ud.category(c) != "Mn"
            ).lower()
            res = _resolve_click(target, norm, executor)
            if isinstance(res, dict) and res.get("success"):
                return _format_result(res.get("message", "Clique executado."))
            fallback = executor.click_text(target)
            if isinstance(fallback, dict) and fallback.get("success"):
                return _format_result(f"Clicou em '{target}'.")
            return _format_result(f"FALHOU: Não encontrei '{target}' na tela.")
        elif name == "click_web_result":
            from actions.web_nav import try_click_web_result
            args = _parse_arguments(raw_args)
            index = int(args.get("index", 0))
            query = (args.get("query") or "").strip()
            label = f"clica no {index + 1}º resultado"
            if query:
                label += f" de {query}"
            web_res = try_click_web_result(
                label,
                executor,
                search_query=query or getattr(executor.web_manager, "last_search_query", ""),
            )
            if web_res and web_res.get("success"):
                return _format_result(web_res.get("message", "OK"))
            return _format_result("FALHOU: não foi possível abrir o resultado da busca.")
        elif name == "open_app":
            args = _parse_arguments(raw_args)
            app = args.get("app_name", "").strip()
            if not app:
                return _format_result("FALHOU: app_name é obrigatório.")
            res = executor.open_app(app)
            if isinstance(res, dict):
                return _format_result(res.get("message", "App aberto.") if res.get("success") else res.get("message", "FALHOU"))
            return _format_result(str(res))
        elif name == "filesystem":
            from actions.filesystem import get_filesystem
            fs = get_filesystem()
            args = _parse_arguments(raw_args)
            action = args.get("action", "list")
            path = args.get("path", "~")
            if action == "list":
                return _format_result(fs.list_dir(path, args.get("pattern", "*")))
            if action == "read":
                return _format_result(fs.read_text(path))
            if action == "write":
                return _format_result(fs.write_text(path, args.get("content", ""), args.get("append", False)))
            if action == "mkdir":
                return _format_result(fs.mkdir(path))
            if action == "move":
                return _format_result(fs.move(path, args.get("destination", "")))
            if action == "delete":
                return _format_result(fs.delete(path))
            if action == "stat":
                return _format_result(fs.stat(path))
            if action == "search":
                return _format_result(fs.search(args.get("query", ""), path))
            return _format_result("FALHOU: action inválida para filesystem.")
        elif name == "desktop_type":
            args = _parse_arguments(raw_args)
            text = args.get("text", "")
            if not text:
                return _format_result("FALHOU: text é obrigatório.")
            res = executor.type_text(text)
            return _format_result(res.get("message", "Digitado.") if res.get("success") else res.get("message", "FALHOU"))
        elif name == "desktop_hotkey":
            args = _parse_arguments(raw_args)
            keys = args.get("keys", "")
            if not keys:
                return _format_result("FALHOU: keys é obrigatório.")
            res = executor.press_key(keys)
            return _format_result(res.get("message", "Tecla pressionada.") if res.get("success") else res.get("message", "FALHOU"))
        elif name == "list_windows":
            return _format_result(executor.wm.list_windows())
        elif name == "focus_window":
            args = _parse_arguments(raw_args)
            return _format_result(executor.wm.focus_window(args.get("title", "")))
        elif name == "control_media":
            from actions.media import get_media
            args = _parse_arguments(raw_args)
            action = args.get("action", "status")
            media = get_media()
            actions_map = {
                "play": media.play, "pause": media.pause, "next": media.next_track,
                "prev": media.prev_track, "stop": media.stop, "status": media.get_status,
                "volume_up": media.volume_up, "volume_down": media.volume_down, "mute": media.mute,
            }
            if action == "volume":
                return _format_result(media.set_volume(int(args.get("level", 50))))
            fn = actions_map.get(action)
            return _format_result(fn() if fn else "FALHOU: action inválida.")
        elif name == "kill_process":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            return _format_result(get_system_tools().kill_process(args.get("pid", 0), args.get("name", "")))
        elif name == "send_notification":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            return _format_result(get_system_tools().send_notification(args.get("title", "Luna"), args.get("message", "")))
        elif name == "system_control":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            st = get_system_tools()
            action = args.get("action", "")
            if action == "brightness":
                return _format_result(st.set_brightness(int(args.get("level", 50))))
            if action == "network":
                return _format_result(st.get_network_status())
            if action == "screenshot":
                return _format_result(st.take_screenshot(args.get("path", "")))
            return _format_result("FALHOU: action inválida para system_control.")
        elif name == "whatsapp_action":
            from actions.whatsapp import get_whatsapp
            args = _parse_arguments(raw_args)
            wa = get_whatsapp()
            action = args.get("action", "status")
            if action == "open":
                return _format_result(wa.open_whatsapp())
            if action == "send":
                return _format_result(wa.send_message(args.get("contact", ""), args.get("message", "")))
            return _format_result(wa.status())
        else:
            return _format_result(f"FALHOU: Ferramenta desconhecida: {name}")
    except Exception as e:
        logger.exception("Erro interno em execute_tool_call")
        return _format_result(f"FALHOU: Erro interno: {str(e)}")
