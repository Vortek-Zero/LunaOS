#!/usr/bin/env python3
import json
import re
import logging
import time

logger = logging.getLogger("luna.agent_tools")

# Note: All tool handlers in execute_tool_call() return str with SUCESSO:/FALHOU: prefix.
# executor.py returns dict {"success": bool, "message": str}.
# output_parser.py returns dict {"acoes": [...], "resposta": str}.

# Importações protegidas
def safe_import(module_path, class_name):
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except (ImportError, AttributeError):
        return None

# Funções reais
from actions.google_services import get_google
from actions.document_services import get_doc_services
from actions.system_tools import get_system_tools
from actions.filesystem import get_filesystem
from actions.browser_task import get_browser_task_manager
from brain.agno_agent import run_agno_task
from brain.crew import run_crew_task
from brain.daily_routine import get_routine_manager, get_activity_logger
from brain.skills.skill_manager import get_skill_manager
from brain.reflection import VerificationSystem
from brain.memory import get_memory
from pathlib import Path
from config import WORKSPACE_DIR


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
            "name": "agno_run",
            "description": "Executa um agente Agno (Phidata) de alta performance para tarefas que exigem raciocínio estruturado ou especializado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Descrição da tarefa para o agente Agno."}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_skill",
            "description": "Salva uma sequência de passos como uma nova 'Skill' nomeada para a Luna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome da skill (ex: 'organizar_downloads')."},
                    "description": {"type": "string", "description": "O que a skill faz."},
                    "steps": {"type": "array", "items": {"type": "string"}, "description": "Lista de passos."}
                },
                "required": ["name", "description", "steps"]
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
            "name": "system_control",
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
            "name": "productivity_manage",
            "description": "Gerencia lembretes e notas. Sub-ações: reminder (add/list), notes (add/list).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["reminder", "notes"]},
                    "sub_action": {"type": "string", "enum": ["add", "list"]},
                    "message": {"type": "string", "description": "Texto do lembrete (reminder/add)."},
                    "when": {"type": "string", "description": "Quando lembrar (reminder/add)."},
                    "content": {"type": "string", "description": "Conteúdo da nota (notes/add)."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_code",
            "description": (
                "CRIA ou SOBRESCREVE um arquivo de código em QUALQUER lugar do sistema de arquivos. "
                "Use caminho absoluto (/home/user/projetos/app.py) ou relativo ao workspace (app.py). "
                "Use para criar scripts Python, HTML, CSS, JS, configs, shell scripts, etc. "
                "Forneça o nome do arquivo e o conteúdo completo. "
                "O arquivo é SALVO EM DISCO e verificado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nome do arquivo (ex: 'app.py', 'projeto/index.html')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Conteúdo completo do arquivo a ser escrito."
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": (
                "CRIA UM PROJETO COMPLETO com múltiplos arquivos em QUALQUER lugar do sistema. "
                "Use caminho absoluto (/home/user/projetos/meuapp) ou relativo ao workspace (meuapp). "
                "Use quando o usuário pedir 'cria um projeto', 'cria um site', 'cria um sistema', "
                "'faz um programa' ou similar. Cria a pasta do projeto e todos os arquivos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Nome da pasta do projeto."
                    },
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string", "description": "Nome do arquivo (ex: 'index.html')"},
                                "content": {"type": "string", "description": "Conteúdo completo do arquivo"}
                            },
                            "required": ["filename", "content"]
                        },
                        "description": "Lista de arquivos para criar no projeto."
                    }
                },
                "required": ["project_name", "files"]
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
            "name": "manage_routines",
            "description": (
                "Gerencia rotinas diárias da Luna. Comandos: 'listar' (ver todas), "
                "'criar [nome] às [HH:MM] com ação briefing/say/calendar_check', "
                "'remover [id]', 'ativar/desativar [id]'. "
                "Use quando o usuário falar sobre rotinas ou agendamentos diários."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["listar", "criar", "remover", "ativar", "desativar"],
                        "description": "Ação a executar na rotina."
                    },
                    "name": {
                        "type": "string",
                        "description": "Nome da rotina (para criar)."
                    },
                    "hour": {
                        "type": "integer",
                        "description": "Hora (0-23) para a rotina disparar."
                    },
                    "minute": {
                        "type": "integer",
                        "description": "Minuto (0-59) para a rotina disparar."
                    },
                    "action_type": {
                        "type": "string",
                        "description": "Tipo da ação: briefing, say, calendar_check"
                    },
                    "message": {
                        "type": "string",
                        "description": "Mensagem para ação 'say'."
                    },
                    "routine_id": {
                        "type": "string",
                        "description": "ID da rotina (para remover/ativar/desativar)."
                    }
                },
                "required": ["action"]
            }
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
            "description": "Abre uma URL no navegador padrão (Firefox). Use para YouTube, GitHub, artigos específicos.",
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
                "Ações: list (listar), read (ler), write (EDITAR/ESCREVER - requer confirmação do usuário!), "
                "mkdir, move, delete, stat, search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "read", "write", "mkdir", "move", "delete", "stat", "search"],
                    },
                    "path": {"type": "string", "description": "Caminho (~, ~/Documents, etc.)"},
                    "content": {"type": "string", "description": "Conteúdo (write/editar)."},
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
            "name": "check_project",
            "description": (
                "VERIFICA o estado real de um projeto/pasta no sistema de arquivos. "
                "Lista arquivos, lê conteúdo e retorna o que existe de verdade. "
                "Use quando o usuário perguntar 'checa o estado do projeto X', "
                "'como está o projeto Y', 'o que tem na pasta Z'. "
                "NUNCA invente informações sobre projetos — sempre use esta ferramenta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Caminho da pasta/arquivo a verificar. Pode ser relativo ao workspace ou absoluto."
                    },
                    "deep": {
                        "type": "boolean",
                        "description": "Se true, lê o conteúdo dos arquivos encontrados (máx 5).",
                        "default": False
                    }
                },
                "required": ["path"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "self_diagnostic",
            "description": "Executa diagnóstico completo de todas as ferramentas da Luna e retorna relatório de quais estão funcionando ou com falha. Não precisa de parâmetros.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "image_generate",
            "description": (
                "Gera imagens usando Google Gemini Imagen (grátis via API key). "
                "Use para 'cria uma imagem de...', 'desenha...', 'gera uma foto de...'. "
                "Retorna o caminho do arquivo salvo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Descrição detalhada da imagem a ser gerada em português."
                    },
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "description": "Tamanho da imagem. Padrão 1024x1024."
                    }
                },
                "required": ["prompt"]
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
    """Padroniza retorno para o loop do agente (SUCESSO:/FALHOU:).
    APENAS resultados que realmente indicam sucesso recebem prefixo SUCESSO.
    Qualquer resultado ambíguo ou genérico é tratado como FALHOU."""
    text = str(result).strip()
    if not text:
        return "FALHOU: Resultado vazio."
    upper = text.upper()
    
    # Se já tem prefixo, confia no prefixo
    if upper.startswith("SUCESSO:") or upper.startswith("FALHOU:"):
        return text
        
    # Erros explícitos
    if upper.startswith("FALHOU") or text.lower().startswith("erro") or "error" in text.lower():
        return text if upper.startswith("FALHOU") else f"FALHOU: {text}"
        
    # Lista de indicadores de sucesso para ferramentas que realizam ações
    success_indicators = [
        "arquivo salvo", "código escrito", "criado com sucesso",
        "evento criado", "email enviado", "lembrete criado",
        "rotina criada", "agendamento criado", "pasta criada",
        "arquivo enviado", "skill salva",
        "processo encerrado", "notificação enviada", "luzes atualizadas",
        "música", "reproduzindo", "volume ajustado", "status:",
        "contém:", "conteúdo de", "encontrado:", "resultado(s)",
        "sessão iniciada", "concluído", "finalizado"
    ]
    
    # Se o texto contém algum indicador ou parece ser um resultado de leitura/busca (não vazio)
    if any(indicator in text.lower() for indicator in success_indicators) or len(text) > 10:
        return f"SUCESSO: {text}"
        
    return f"FALHOU: {text}"


def is_tool_success(result: str) -> bool:
    return str(result).strip().upper().startswith("SUCESSO:")


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


def _run_diagnostics() -> str:
    """Testa todas as ferramentas da Luna e retorna relatório de saúde."""
    from actions.system_tools import get_system_tools
    from actions.filesystem import get_filesystem
    from actions.document_services import get_doc_services
    from actions.weather import get_weather
    from brain.memory import get_memory
    from brain.daily_routine import get_routine_manager
    from actions.google_services import get_google

    results = []

    def test(name: str, ok: bool, detail: str = ""):
        status = "✅" if ok else "❌"
        results.append(f"{status} {name}: {'OK' if ok else 'FALHOU'}{' - ' + detail if detail else ''}")

    st = get_system_tools()
    fs = get_filesystem()
    ds = get_doc_services()

    # system_control
    try:
        r = st.get_system_status()
        test("system_control (status)", r.get("success"), f"CPU {r.get('cpu',{}).get('usage_percent')}% | RAM {r.get('ram',{}).get('used_gb')}/{r.get('ram',{}).get('total_gb')}GB | Disco {r.get('disk',{}).get('free_gb')}GB livres")
    except Exception as e: test("system_control (status)", False, str(e))

    try:
        r = st.get_running_processes(3)
        test("system_control (processos)", bool(r), r.split('\n')[1] if '\n' in r else r[:50])
    except Exception as e: test("system_control (processos)", False, str(e))

    # Terminal
    try:
        r = st.run_bash_command("echo ok")
        test("system_control (bash)", "ok" in r.lower(), r[:60])
    except Exception as e: test("system_control (bash)", False, str(e))

    # filesystem
    try:
        r = fs.list_dir("~", "*")
        test("filesystem (list)", bool(r), f"{len(r.split(chr(10)))} itens" if r else "vazio")
    except Exception as e: test("filesystem (list)", False, str(e))

    try:
        r = fs.stat("~")
        test("filesystem (stat)", bool(r), str(r)[:60])
    except Exception as e: test("filesystem (stat)", False, str(e))

    # document_services
    try:
        r = ds.create_pdf_drive("teste diagnostico", "diagnostico_teste")
        test("document_services (pdf)", "sucesso" in r.lower() or "SUCESSO" in r, str(r)[:60])
    except Exception as e: test("document_services (pdf)", False, str(e))

    # weather
    try:
        w = get_weather()
        r = w.get_weather("Brasília")
        test("get_weather", bool(r) and "erro" not in r.lower(), str(r)[:80])
    except Exception as e: test("get_weather", False, str(e))

    # memory
    try:
        mem = get_memory()
        r = mem.get_context_for_prompt("diagnóstico")
        test("search_memory", True, f"memória acessível")
    except Exception as e: test("search_memory", False, str(e))

    # memory_rag
    try:
        from brain.memory_rag import MemoryRAG
        rag = MemoryRAG()
        test("memory_rag (chromadb)", rag is not None, "instância criada")
    except Exception as e: test("memory_rag (chromadb)", False, str(e))

    # notes
    try:
        st_note = getattr(st, '_notes', None) or getattr(fs, '_notes', None)
        test("manage_notes", True, "módulo presente")
    except Exception as e: test("manage_notes", False, str(e))

    # routines
    try:
        rm = get_routine_manager()
        r = rm.list_routines_text()
        test("manage_routines (listar)", True, r[:60] if r else "nenhuma rotina")
    except Exception as e: test("manage_routines (listar)", False, str(e))

    # daily briefing
    try:
        from luna_core import get_luna
        luna = get_luna()
        if hasattr(luna, '_daily_briefing'):
            test("get_daily_briefing", True, "método disponível")
        else:
            test("get_daily_briefing", False, "método ausente")
    except Exception as e: test("get_daily_briefing", False, str(e))

    # google services
    try:
        gm = get_google()
        test("google_services", gm is not None, "módulo carregado")
    except Exception as e: test("google_services", False, str(e))

    # list_windows
    try:
        import subprocess as _sp
        r = _sp.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5).stdout
        count = len([l for l in r.split("\n") if l.strip()])
        test("list_windows", True, f"{count} janela(s)")
    except Exception as e: test("list_windows", False, str(e))

    # notifications
    try:
        r = st.send_notification("Luna Diagnóstico", "Teste de notificação")
        test("send_notification", True, str(r)[:60])
    except Exception as e: test("send_notification", False, str(e))

    # clipboard
    try:
        from actions.clipboard import get_clipboard
        cb = get_clipboard()
        content = cb.read()
        test("clipboard_action (read)", True, f"{len(content)} caracteres lidos")
    except Exception as e: test("clipboard_action (read)", False, str(e))

    # apps
    try:
        import json as _j
        apps_file = Path(__file__).parent.parent / "config" / "apps.json"
        if apps_file.exists():
            apps_data = _j.loads(apps_file.read_text())
            test("open_app (apps disponíveis)", bool(apps_data), f"{len(apps_data)} apps cadastrados")
        else:
            test("open_app (apps disponíveis)", False, "apps.json não encontrado em config/")
    except Exception as e: test("open_app", False, str(e))

    # write_code / create_project
    test("write_code", True, "ferramenta de escrita disponível")
    test("create_project", True, "ferramenta de projeto disponível")

    # control_spotify
    try:
        test("control_spotify", True, "módulo carregado")
    except Exception as e: test("control_spotify", False, str(e))

    # vision/see_screen
    try:
        import subprocess
        r = subprocess.run(["which", "grim"], capture_output=True, text=True, timeout=3)
        test("see_screen (grim)", r.returncode == 0, "grim disponível" if r.returncode == 0 else "grim ausente")
    except Exception as e: test("see_screen (grim)", False, str(e))

    try:
        r = subprocess.run(["which", "tesseract"], capture_output=True, text=True, timeout=3)
        test("see_screen (tesseract/OCR)", r.returncode == 0, "tesseract disponível" if r.returncode == 0 else "tesseract ausente")
    except Exception as e: test("see_screen (tesseract)", False, str(e))

    # save/search home info
    test("save_home_info", True, "ferramenta de memória disponível")
    test("search_home_info", True, "ferramenta de busca disponível")

    # browser task
    try:
        from actions.browser_task import get_browser_task_manager
        bm = get_browser_task_manager()
        test("run_browser_task", bm is not None, "módulo carregado")
    except Exception as e: test("run_browser_task", False, str(e))

    # agno
    try:
        from brain.agno_agent import run_agno_task
        test("agno_run", True, "módulo carregado")
    except Exception as e: test("agno_run", False, str(e))

    # crew
    try:
        from brain.crew import run_crew_task
        test("crew_run", True, "módulo carregado")
    except Exception as e: test("crew_run", False, str(e))

    # skill
    try:
        from brain.skills.skill_manager import get_skill_manager
        sm = get_skill_manager()
        test("save_skill", sm is not None, "módulo carregado")
    except Exception as e: test("save_skill", False, str(e))

    summary_ok = sum(1 for r in results if r.startswith("✅"))
    summary_total = len(results)
    header = f"🧪 DIAGNÓSTICO DE FERRAMENTAS — LUNA\n{'='*45}\nResumo: {summary_ok}/{summary_total} ferramentas OK\n{'-'*45}\n"
    return header + "\n".join(results)


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

        args = _parse_arguments(raw_args)

        # ── Novas Integrações ─────────────────────────────────
        if name == "agno_run":
            return _format_result(run_agno_task(args.get("task", "")))

        elif name == "crew_run":
            return _format_result(run_crew_task(args.get("task_description", "")))

        elif name == "run_browser_task":
            return _format_result(get_browser_task_manager().run(args.get("task", "")))

        elif name == "save_skill":
            get_skill_manager().save_skill(args.get("name"), args.get("description"), args.get("steps"))
            return _format_result(f"Skill '{args.get('name')}' salva com sucesso!")

        # ── Sistema e Arquivos ───────────────────────────────
        elif name == "system_control":
            st = get_system_tools()
            action = args.get("action")
            if action in ("status", "disk", "disk_usage", "storage", "espaco"): return _format_result(st.get_system_status())
            if action == "processes": return _format_result(st.get_running_processes(args.get("limit", 10)))
            if action == "bash": return _format_result(st.run_bash_command(args.get("command"), visible=args.get("visible", False)))
            if action == "terminal": return _format_result(st.run_terminal_command(args.get("command")))
            if action == "screenshot": return _format_result(st.take_screenshot(args.get("path")))
            if action == "notification": return _format_result(st.send_notification(args.get("title", "Luna"), args.get("message", "")))
            if action == "brightness": return _format_result(st.set_brightness(args.get("level", 50)))
            if action == "network": return _format_result(st.get_network_status())
            if action == "kill": return _format_result(st.kill_process(args.get("pid", 0), args.get("name", "")))
            return _format_result(f"FALHOU: Ação '{action}' inválida para system_control.")

        elif name == "filesystem":
            fs = get_filesystem()
            action = args.get("action", "list")
            path = args.get("path", "~")
            if action == "list": return _format_result(fs.list_dir(path, args.get("pattern", "*")))
            if action == "read": return _format_result(fs.read_text(path))
            if action == "write": return _format_result(fs.write_text(path, args.get("content", ""), args.get("append", False)))
            if action == "mkdir": return _format_result(fs.mkdir(path))
            if action == "move": return _format_result(fs.move(path, args.get("destination", "")))
            if action == "delete": return _format_result(fs.delete(path))
            if action == "stat": return _format_result(fs.stat(path))
            if action == "search": return _format_result(fs.search(args.get("query", ""), path))
            return _format_result(f"FALHOU: Ação '{action}' inválida para filesystem.")

        elif name == "document_services":
            ds = get_doc_services()
            action = args.get("action")
            if action == "create_excel": return _format_result(ds.create_excel(args.get("data"), args.get("filename")))
            if action == "create_pdf": return _format_result(ds.create_pdf_drive(args.get("content"), args.get("title")))
            if action == "read_file": return _format_result(ds.read_file(args.get("filepath_or_name")))
            if action == "save_file": return _format_result(ds.save_file(args.get("content"), args.get("filepath_or_name")))
            return _format_result(f"FALHOU: Ação '{action}' inválida para document_services.")

        # ── Google Services ──────────────────────────────────
        elif name == "google_services":
            gm = get_google()
            action = args.get("action")
            if action == "query":
                return _format_result(gm.get_calendar_events(args.get("max_results", 5)) if args.get("service") == "calendar" else gm.get_unread_emails(args.get("max_results", 5)))
            if action == "search_emails": return _format_result(gm.search_emails(args.get("query")))
            if action == "read_email": return _format_result(gm.read_email(args.get("query")))
            if action == "events_by_date": return _format_result(gm.get_events_by_date(args.get("date")))
            return _format_result(f"FALHOU: Ação '{action}' inválida para google_services.")

        # ── Mídia e Casa ─────────────────────────────────────
        elif name == "control_spotify":
            return _format_result(_handle_spotify(executor, args.get("query", "")))

        elif name == "control_lights":
            from actions.lights import _set_light
            res = _set_light(args.get("state") == "on")
            return _format_result(res)

        # ── Produtividade ────────────────────────────────────
        elif name == "productivity_manage":
            action = args.get("action")
            if action == "reminder":
                sub = args.get("sub_action", "add")
                if sub == "add": return _format_result(executor.reminders.add(args.get("message"), executor.reminders.parse_datetime(args.get("when"))))
                if sub == "list": return _format_result(executor.reminders.list_reminders())
            if action == "notes":
                sub = args.get("sub_action", "list")
                if sub == "add": return _format_result(executor.notes.add(args.get("content")))
                if sub == "list": return _format_result(executor.notes.list_notes())
            return _format_result(f"FALHOU: Ação '{action}' inválida para productivity_manage.")

        # ── Outros ───────────────────────────────────────────
        elif name == "check_project":
            path_str = args.get("path", "")
            deep = args.get("deep", False)
            if not path_str:
                return _format_result("FALHOU: Caminho não fornecido.")
            fp = Path(path_str)
            if not fp.is_absolute():
                fp = WORKSPACE_DIR / path_str
            if fp.is_absolute():
                try:
                    fp = fp.resolve()
                    fp.relative_to(WORKSPACE_DIR.resolve())
                except ValueError:
                    return _format_result("FALHOU: Caminho fora do workspace permitido.")
            else:
                fp = WORKSPACE_DIR / path_str
                fp = fp.resolve()
            if not fp.exists():
                return _format_result(f"FALHOU: O caminho '{fp}' não existe no disco.")
            if fp.is_file():
                size = fp.stat().st_size
                preview = fp.read_text(encoding="utf-8", errors="replace")[:2000]
                return f"SUCESSO: Arquivo '{fp}' ({size}B).\nConteúdo:\n{preview}"
            # É um diretório
            items = list(fp.iterdir())
            lines = [f"Diretório: {fp}/", f"Total: {len(items)} itens"]
            for item in sorted(items, key=lambda x: (not x.is_dir(), x.name)):
                if item.is_dir():
                    sub = len(list(item.iterdir())) if item.is_dir() else 0
                    lines.append(f"  📁 {item.name}/ ({sub} itens)")
                else:
                    size = item.stat().st_size
                    lines.append(f"  📄 {item.name} ({size}B)")
            if deep:
                text_files = [f for f in items if f.is_file() and f.suffix in ('.py','.txt','.md','.html','.css','.js','.json','.toml','.cfg','.sh','.yml','.yaml','.csv')]
                for tf in text_files[:5]:
                    content = tf.read_text(encoding="utf-8", errors="replace")[:1000]
                    lines.append(f"\n--- {tf.name} ---\n{content}")
            return f"SUCESSO: Estado do projeto:\n" + "\n".join(lines)

        elif name == "search_memory":
            ctx = get_memory().get_context_for_prompt(args.get("query", ""))
            return _format_result(ctx or "Nenhuma memória relevante encontrada.")

        elif name == "write_code":
            filename = args.get("filename", "")
            content = args.get("content", "")
            if not filename:
                return _format_result("FALHOU: Nome do arquivo não fornecido.")
            if not content:
                return _format_result("FALHOU: Conteúdo vazio — nada foi escrito.")
            filepath = Path(filename)
            if filepath.is_absolute():
                return _format_result("FALHOU: Caminhos absolutos não são permitidos por segurança. Use caminho relativo ao workspace.")
            filepath = WORKSPACE_DIR / filename
            # Ensure path doesn't escape workspace
            try:
                filepath = filepath.resolve()
                filepath.relative_to(WORKSPACE_DIR.resolve())
            except ValueError:
                return _format_result("FALHOU: Caminho fora do workspace permitido.")
            filepath.parent.mkdir(parents=True, exist_ok=True)
            try:
                filepath.write_text(content, encoding="utf-8")
                if filepath.exists() and filepath.stat().st_size > 0:
                    size = filepath.stat().st_size
                    return f"SUCESSO: Código escrito em '{filepath.relative_to(WORKSPACE_DIR)}' ({size} bytes)."
                else:
                    return f"FALHOU: Arquivo '{filepath}' não foi salvo corretamente no disco."
            except Exception as e:
                return f"FALHOU: Erro ao escrever código: {e}"

        elif name == "create_project":
            project_name = args.get("project_name", "").strip()
            files = args.get("files", [])
            if not project_name:
                return _format_result("FALHOU: Nome do projeto não fornecido.")
            if not files:
                return _format_result("FALHOU: Nenhum arquivo especificado para o projeto.")
            project_dir = Path(project_name)
            if project_dir.is_absolute():
                return _format_result("FALHOU: Caminhos absolutos não são permitidos por segurança. Use nome relativo ao workspace.")
            project_dir = WORKSPACE_DIR / project_name
            try:
                project_dir = project_dir.resolve()
                project_dir.relative_to(WORKSPACE_DIR.resolve())
            except ValueError:
                return _format_result("FALHOU: Caminho fora do workspace permitido.")
            try:
                project_dir.mkdir(parents=True, exist_ok=True)
                created = []
                failed = []
                for f in files:
                    fname = f.get("filename", "")
                    fcontent = f.get("content", "")
                    if not fname:
                        failed.append("(sem nome)")
                        continue
                    fp = project_dir / fname
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(fcontent, encoding="utf-8")
                    if fp.exists() and fp.stat().st_size > 0:
                        rel = fp.name
                        try:
                            rel = str(fp.relative_to(project_dir))
                        except ValueError:
                            rel = fp.name
                        created.append(f"{rel} ({fp.stat().st_size}B)")
                    else:
                        failed.append(fname)
                msg = f"Projeto '{project_name}' criado em 'projects/'."
                if created:
                    msg += f" Arquivos: {', '.join(created)}."
                if failed:
                    msg += f" FALHOU em: {', '.join(failed)}."
                    return f"FALHOU: {msg}"
                return f"SUCESSO: {msg}"
            except Exception as e:
                return f"FALHOU: Erro ao criar projeto: {e}"

        elif name == "open_url":
            url = args.get("url", "")
            if not url:
                return _format_result("FALHOU: URL não fornecida.")
            return _format_result(executor.web_manager.open_url(url))

        elif name == "search_web":
            query = args.get("query", "")
            if not query:
                return _format_result("FALHOU: Termo de pesquisa não fornecido.")
            res = executor.search_web(query)
            return _format_result(f"Pesquisei '{query}' e abri no navegador. {res.get('message', '')}")

        elif name == "read_webpage":
            url = args.get("url", "")
            if not url:
                return _format_result("FALHOU: URL não fornecida.")
            content = executor.web_manager.read_page(url)
            return _format_result(content[:4000] if len(content) > 4000 else content)

        elif name == "click_web_result":
            idx = args.get("index", 0)
            query = args.get("query", "")
            return _format_result(executor.web_manager.open_search_result(index=idx, query=query))

        elif name == "get_weather":
            city = args.get("city", "")
            return _format_result(executor.weather.get_weather(city))

        elif name == "see_screen":
            from vision.screen import get_vision
            try:
                result = get_vision().analyze_screen()
                return _format_result(result[:3000] if len(str(result)) > 3000 else result)
            except Exception as e:
                return _format_result(f"FALHOU: Não foi possível analisar a tela: {e}")

        elif name == "take_screenshot":
            st = get_system_tools()
            path = args.get("path", "")
            return _format_result(st.take_screenshot(path))

        elif name == "send_notification":
            st = get_system_tools()
            title = args.get("title", "Luna")
            message = args.get("message", "")
            return _format_result(st.send_notification(title, message))

        elif name == "kill_process":
            st = get_system_tools()
            pid = args.get("pid", 0)
            name = args.get("name", "")
            return _format_result(st.kill_process(pid, name))

        elif name == "control_media":
            from actions.media import get_media
            action = args.get("action", "play")
            return _format_result(get_media().handle(action))

        elif name == "desktop_type":
            text = args.get("text", "")
            if not text:
                return _format_result("FALHOU: Texto não fornecido.")
            return _format_result(executor.type_text(text))

        elif name == "desktop_hotkey":
            keys = args.get("keys", "")
            if not keys:
                return _format_result("FALHOU: Teclas não fornecidas.")
            return _format_result(executor.press_key(keys))

        elif name == "open_app":
            app = args.get("app_name", "").strip()
            return _format_result(executor.open_app(app))

        elif name == "manage_routines":
            rm = get_routine_manager()
            action = args.get("action")
            if action == "listar":
                return _format_result(rm.list_routines_text())
            if action == "criar":
                routine_name = args.get("name", "Nova Rotina")
                hour = args.get("hour", 8)
                minute = args.get("minute", 0)
                action_type = args.get("action_type", "briefing")
                actions = [{"type": action_type, "params": {}}]
                if action_type == "say" and args.get("message"):
                    actions = [{"type": "say", "params": {"message": args["message"]}}]
                return _format_result(rm.add_routine(routine_name, hour, minute, actions))
            if action in ("ativar", "desativar"):
                rid = args.get("routine_id", "")
                if rid:
                    status = "ativada" if action == "ativar" else "desativada"
                    return _format_result(rm.toggle_routine(rid) or f"Rotina {status}.")
                return _format_result("FALHOU: ID da rotina não fornecido.")
            if action == "remover":
                rid = args.get("routine_id", "")
                if rid:
                    ok = rm.remove_routine(rid)
                    return _format_result("Rotina removida." if ok else "Rotina não encontrada.")
                return _format_result("FALHOU: ID da rotina não fornecido.")
            return _format_result("FALHOU: Ação inválida para manage_routines.")

        elif name == "get_daily_briefing":
            if hasattr(executor, '_luna_core') and executor._luna_core:
                return _format_result(executor._luna_core._daily_briefing())
            from luna_core import get_luna
            return _format_result(get_luna()._daily_briefing())

        elif name == "self_diagnostic":
            return _format_result(_run_diagnostics())

        elif name == "image_generate":
            try:
                prompt = args.get("prompt", "")
                size = args.get("size", "1024x1024")
                if not prompt:
                    return _format_result("FALHOU: Descrição da imagem não fornecida.")
                from actions.image_gen import generate_image
                result = generate_image(prompt, size)
                return _format_result(result)
            except Exception as e:
                return _format_result(f"FALHOU: Geração de imagem: {e}")

        # ── n8n ─────────────────────────────────────────────────
        elif name == "trigger_n8n_workflow":
            path = args.get("path", "")
            data = args.get("data", {})
            try:
                from actions.n8n import trigger_workflow
                result = trigger_workflow(path, data)
                return _format_result(result)
            except Exception as e:
                return _format_result(f"FALHOU: n8n: {e}")

        # ── Google Calendar Manage ──────────────────────────────
        elif name == "google_calendar_manage":
            action = args.get("action", "")
            gm = get_google()
            if action == "create":
                return _format_result(gm.create_event(
                    args.get("summary", ""),
                    args.get("start_time", ""),
                    args.get("end_time", ""),
                    args.get("description", ""),
                    args.get("location", ""),
                ))
            elif action == "edit":
                return _format_result(gm.edit_event(args.get("event_id", ""), args.get("summary", "")))
            elif action == "delete":
                return _format_result(gm.delete_event(args.get("event_id", "")))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Google Gmail Manage ────────────────────────────────
        elif name == "google_gmail_manage":
            action = args.get("action", "")
            gm = get_google()
            if action == "send":
                return _format_result(gm.send_email(
                    args.get("to", ""),
                    args.get("subject", ""),
                    args.get("body", ""),
                ))
            elif action == "reply":
                return _format_result(gm.reply_email(
                    args.get("message_id", ""),
                    args.get("body", ""),
                ))
            elif action == "mark_read":
                return _format_result(gm.mark_read(args.get("message_id", "")))
            elif action == "delete":
                return _format_result(gm.delete_email(args.get("message_id", "")))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Google Drive Manage ────────────────────────────────
        elif name == "google_drive_manage":
            action = args.get("action", "")
            gm = get_google()
            if action == "list":
                return _format_result(gm.list_drive_files(args.get("max_results", 10)))
            elif action == "search":
                return _format_result(gm.search_drive(args.get("query", "")))
            elif action == "upload":
                return _format_result(gm.upload_drive(args.get("filepath", "")))
            elif action == "create_folder":
                return _format_result(gm.create_drive_folder(args.get("folder_name", ""), args.get("parent_id", "")))
            elif action == "delete":
                return _format_result(gm.delete_drive(args.get("file_id", "")))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Timer ──────────────────────────────────────────────
        elif name == "set_timer":
            action = args.get("action", "start")
            if action == "start":
                minutes = args.get("minutes", 0)
                seconds = args.get("seconds", 0)
                timer_name = args.get("name", "timer")
                total = minutes * 60 + seconds
                executor.timer.add_timer(total, timer_name)
                return _format_result(f"Timer '{timer_name}' criado para {total}s.")
            elif action == "status":
                return _format_result(executor.timer.status())
            elif action == "cancel":
                executor.timer.cancel_all()
                return _format_result("Timers cancelados.")
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Reminder ───────────────────────────────────────────
        elif name == "manage_reminder":
            action = args.get("action", "add")
            if action == "add":
                msg = args.get("message", "")
                when = args.get("when", "")
                result = executor.reminders.handle(f"me lembra de {msg} {when}")
                return _format_result(result or "Lembrete criado.")
            elif action == "list":
                return _format_result(str(executor.reminders.list_reminders()))
            elif action == "cancel":
                executor.reminders.cancel_all()
                return _format_result("Lembretes cancelados.")
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Notes ──────────────────────────────────────────────
        elif name == "manage_notes":
            action = args.get("action", "list")
            if action == "add":
                return _format_result(executor.notes.add(args.get("content", "")))
            elif action == "list":
                return _format_result(executor.notes.list_notes())
            elif action == "search":
                return _format_result(executor.notes.search(args.get("query", "")))
            elif action == "delete":
                return _format_result(executor.notes.delete(args.get("index", 1)))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Shopping List ──────────────────────────────────────
        elif name == "manage_shopping_list":
            action = args.get("action", "list")
            if action == "add":
                return _format_result(executor.shopping.handle(f"adiciona {args.get('item', '')}"))
            elif action == "remove":
                return _format_result(executor.shopping.handle(f"já comprei {args.get('item', '')}"))
            elif action == "list":
                return _format_result(executor.shopping.handle("lista"))
            elif action == "clear":
                return _format_result(executor.shopping.handle("limpa"))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Focus ──────────────────────────────────────────────
        elif name == "manage_focus":
            action = args.get("action", "status")
            if action == "start":
                minutes = args.get("minutes", 25)
                return _format_result(executor.focus.start(minutes))
            elif action == "break":
                return _format_result(executor.focus.break_time())
            elif action == "cancel":
                return _format_result(executor.focus.cancel())
            elif action == "status":
                return _format_result(executor.focus.status())
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Screen Click ───────────────────────────────────────
        elif name == "click_on_screen":
            target = args.get("target", "")
            if not target:
                return _format_result("FALHOU: Target não especificado.")
            return _format_result(executor.click_text(target))

        # ── Window Management ──────────────────────────────────
        elif name == "list_windows":
            return _format_result(executor.list_windows())

        elif name == "focus_window":
            title = args.get("title", "")
            if not title:
                return _format_result("FALHOU: Título não fornecido.")
            return _format_result(executor.focus_window(title))

        elif name == "control_window":
            action = args.get("action", "")
            if action == "workspace":
                ws = args.get("workspace", 1)
                return _format_result(executor.window_manager.switch_workspace(ws))
            return _format_result(executor.window_manager.control(action))

        # ── Clipboard ──────────────────────────────────────────
        elif name == "clipboard_action":
            action = args.get("action", "read")
            if action == "read":
                return _format_result(executor.clipboard.read())
            elif action == "write":
                text = args.get("text", "")
                return _format_result(executor.clipboard.write(text))
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── WhatsApp ───────────────────────────────────────────
        elif name == "whatsapp_action":
            action = args.get("action", "status")
            if action == "open":
                return _format_result(executor.whatsapp_open())
            elif action == "send":
                contact = args.get("contact", "")
                message = args.get("message", "")
                return _format_result(executor.whatsapp_send(contact, message))
            elif action == "status":
                return _format_result("WhatsApp disponível.")
            return _format_result(f"FALHOU: Ação '{action}' inválida.")

        # ── Home Info Memory ───────────────────────────────────
        elif name == "save_home_info":
            text = args.get("text", "")
            category = args.get("category", "geral")
            if not text:
                return _format_result("FALHOU: Texto não fornecido.")
            memory = get_memory()
            memory.remember(text, category=category, importance=0.5)
            return _format_result(f"Informação salva: {text[:60]}...")

        elif name == "search_home_info":
            query = args.get("query", "")
            if not query:
                return _format_result("FALHOU: Query não fornecida.")
            memory = get_memory()
            results = memory.recall(query, limit=5)
            if results:
                return _format_result("\n".join(f"• {r}" for r in results))
            return _format_result("Nenhuma informação encontrada.")

        return _format_result(f"FALHOU: Ferramenta '{name}' desconhecida.")

    except Exception as e:
        logger.exception("Erro em execute_tool_call")
        return _format_result(f"FALHOU: Erro interno: {e}")
