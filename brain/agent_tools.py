#!/usr/bin/env python3
import json
import re
import logging

logger = logging.getLogger("luna.agent_tools")

from actions.google_services import get_google


LUNA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_luna_command",
            "description": (
                "Executa UMA ação no sistema da Luna. Chame uma vez por intenção. "
                "Comandos disponíveis:\n"
                "luna-spotify <busca|next|prev|pause|play|volume N> — música\n"
                "luna-lights <on|off> — luz física da sala\n"
                "luna-search <query> — pesquisa na web\n"
                "luna-app <nome> — abre aplicativo\n"
                "luna-click <alvo> — clica em elemento na tela ou no browser. "
                "  Use para: 'clica no primeiro link', 'clica no segundo resultado', "
                "  'clica no vídeo', 'clica no botão X', 'clica em Entrar'. "
                "  Exemplos: luna-click 'primeiro link', luna-click 'segundo resultado', "
                "  luna-click 'terceiro vídeo', luna-click 'botão pesquisar', luna-click 'Entrar'\n"
                "luna-browser <tarefa ou URL> — agente autônomo para tarefas complexas no browser "
                "  (preencher formulários, navegar por múltiplas páginas, fazer login)\n"
                "luna-router <ação> — funções do sistema: timer, lembrete, notas, lista de compras, clima"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "Comando completo. Exemplos: "
                            "'luna-spotify the weeknd', 'luna-lights off', "
                            "'luna-search python tutorial', 'luna-app firefox', "
                            "'luna-click primeiro link', 'luna-click segundo resultado', "
                            "'luna-click terceiro vídeo', 'luna-click botão enviar', "
                            "'luna-browser abra o youtube e pesquise lofi music', "
                            "'luna-router timer de 10 minutos'"
                        )
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_query",
            "description": "Consulta o Google Calendar ou Gmail para obter próximos compromissos ou emails não lidos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "enum": ["calendar", "gmail"],
                        "description": "Qual serviço consultar: 'calendar' ou 'gmail'."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Número máximo de resultados a retornar.",
                        "default": 5
                    }
                },
                "required": ["service"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_send_email",
            "description": "Envia um email via Gmail com suporte opcional a anexar arquivos da pasta Luna-programming.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Email do destinatário."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Assunto do email."
                    },
                    "body": {
                        "type": "string",
                        "description": "Corpo do email."
                    },
                    "attachments": {
                        "type": "string",
                        "description": "Opcional. Nomes de arquivos separados por vírgula na pasta Luna-programming (ex: 'main.py, nota.txt') ou caminhos absolutos."
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_create_event",
            "description": "Cria um compromisso no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Título do evento."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Início em ISO 8601 (ex: '2026-05-21T14:00:00-03:00') ou YYYY-MM-DD para dia inteiro."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Opcional. Fim em ISO 8601 ou YYYY-MM-DD. Se omitido, dura 1 hora."
                    },
                    "description": {
                        "type": "string",
                        "description": "Opcional. Descrição."
                    },
                    "location": {
                        "type": "string",
                        "description": "Opcional. Local ou link."
                    },
                    "attendees": {
                        "type": "string",
                        "description": "Opcional. Emails de participantes separados por vírgula."
                    }
                },
                "required": ["summary", "start_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_edit_event",
            "description": "Edita campos de um compromisso existente no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID do evento a ser modificado."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Novo título do evento."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Novo início (ISO 8601 ou YYYY-MM-DD)."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Novo fim (ISO 8601 ou YYYY-MM-DD)."
                    },
                    "description": {
                        "type": "string",
                        "description": "Nova descrição."
                    },
                    "location": {
                        "type": "string",
                        "description": "Novo local."
                    }
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_delete_event",
            "description": "Deleta um compromisso no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID do evento a ser deletado."
                    }
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_events_by_date",
            "description": "Lista todos os compromissos de uma data específica no Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Data no formato YYYY-MM-DD."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Máximo de resultados.",
                        "default": 20
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search_emails",
            "description": "Pesquisa emails no Gmail usando a busca padrão (ex: 'from:pera', 'subject:luna').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query de busca."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Máximo de resultados.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_read_email",
            "description": "Lê o corpo e detalhes de um email específico pelo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "ID do email."
                    }
                },
                "required": ["message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_reply_email",
            "description": "Responde a um email recebido no Gmail pelo ID do email original.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "ID do email original."
                    },
                    "body": {
                        "type": "string",
                        "description": "Corpo da resposta."
                    }
                },
                "required": ["message_id", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_forward_email",
            "description": "Encaminha um email no Gmail para um destinatário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "ID do email original."
                    },
                    "to": {
                        "type": "string",
                        "description": "Email do destinatário."
                    },
                    "extra_text": {
                        "type": "string",
                        "description": "Opcional. Texto a ser inserido no topo."
                    }
                },
                "required": ["message_id", "to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_mark_read",
            "description": "Marca um email no Gmail como lido pelo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "ID do email."
                    }
                },
                "required": ["message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_delete_email",
            "description": "Move um email no Gmail para a lixeira pelo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "ID do email."
                    }
                },
                "required": ["message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_list_files",
            "description": "Lista os arquivos gerados pela Luna na pasta Luna-programming (imagens, códigos, textos, etc.) para que você possa localizá-los e anexá-los se necessário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Opcional. Filtro glob (ex: '*.py', '*.png'). Padrão é '*'.",
                        "default": "*"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_upload",
            "description": "Faz o upload de um arquivo do workspace Luna-programming ou do sistema para o Google Drive e ativa um link de compartilhamento público.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath_or_name": {
                        "type": "string",
                        "description": "Nome do arquivo no workspace (ex: 'main.py') ou caminho absoluto."
                    },
                    "folder_id": {
                        "type": "string",
                        "description": "Opcional. ID da pasta no Google Drive onde o arquivo será salvo."
                    }
                },
                "required": ["filepath_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_list",
            "description": "Lista arquivos recentes que estão salvos no seu Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Número máximo de arquivos para listar (padrão é 10).",
                        "default": 10
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_search",
            "description": "Pesquisa arquivos no seu Google Drive pelo nome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca (nome do arquivo ou parte dele)."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Máximo de resultados (padrão 10).",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_create_folder",
            "description": "Cria uma nova pasta no seu Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_name": {
                        "type": "string",
                        "description": "Nome da pasta a ser criada."
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Opcional. ID da pasta pai onde ela será criada."
                    }
                },
                "required": ["folder_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_drive_delete",
            "description": "Move um arquivo ou pasta do seu Google Drive para a lixeira pelo ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "ID do arquivo ou pasta a ser deletado."
                    }
                },
                "required": ["file_id"]
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
            "name": "create_excel",
            "description": "Cria uma planilha Excel (.xlsx) a partir de uma lista de dados (objetos JSON) e salva no workspace Luna-programming.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object"
                        },
                        "description": "Lista de objetos/dicionários contendo as colunas e valores."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Nome do arquivo (ex: 'vendas.xlsx')."
                    }
                },
                "required": ["data", "filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_pdf_drive",
            "description": "Gera um documento PDF exportado via Google Drive a partir de um texto e salva localmente e na nuvem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Conteúdo de texto que será o corpo do PDF."
                    },
                    "title": {
                        "type": "string",
                        "description": "Título/nome do arquivo PDF (ex: 'Relatório Semanal')."
                    }
                },
                "required": ["content", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê e extrai o texto de arquivos locais (.txt, .csv, .xlsx, .pdf).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath_or_name": {
                        "type": "string",
                        "description": "Nome do arquivo no workspace (ex: 'notas.txt') ou caminho absoluto."
                    }
                },
                "required": ["filepath_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": "Salva ou escreve conteúdo de texto em um arquivo local no workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Conteúdo de texto a ser salvo no arquivo."
                    },
                    "filepath_or_name": {
                        "type": "string",
                        "description": "Nome do arquivo no workspace (ex: 'relatorio.txt') ou caminho absoluto."
                    }
                },
                "required": ["content", "filepath_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Retorna o status atual de hardware do sistema (uso de CPU, núcleos, média de carga, uso de memória RAM e espaço em disco disponível).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_running_processes",
            "description": "Lista os processos em execução no sistema operacional que mais estão consumindo CPU ou memória.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Número máximo de processos para retornar. Padrão é 10.",
                        "default": 10
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash_command",
            "description": "Executa um comando síncrono no terminal bash. Use apenas para comandos seguros e úteis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "O comando de terminal completo a ser executado."
                    }
                },
                "required": ["command"]
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

        if name == "run_luna_command":
            args = _parse_arguments(raw_args)
            cmd = args.get("command", "").strip()

            if not cmd:
                return "FALHOU: Comando vazio recebido."

            if _is_blocked(cmd):
                logger.warning("Comando bloqueado por segurança: %s", cmd)
                return f"FALHOU: Comando bloqueado por política de segurança."

            logger.info("Executando: %s", cmd)
            cmd_lower = cmd.lower()

            # Existing command handling (spotify, lights, search, app, router, click, browser)
            if cmd_lower.startswith("luna-spotify"):
                query = cmd[12:].strip().strip('"\'')
                if not query:
                    return "FALHOU: luna-spotify precisa de uma música ou artista."
                result = _handle_spotify(executor, query)
                return f"SUCESSO: {result}"

            elif cmd_lower.startswith("luna-lights"):
                state = cmd[11:].strip().strip('"\'').lower()
                if state not in ("on", "off"):
                    return "FALHOU: luna-lights aceita apenas 'on' ou 'off'."
                action = "acender luzes" if state == "on" else "apagar luzes"
                res = executor.lights.handle(action)
                return f"SUCESSO: {res or 'Luzes atualizadas.'}"

            elif cmd_lower.startswith("luna-search"):
                query = cmd[11:].strip().strip('"\'')
                if not query:
                    return "FALHOU: luna-search precisa de uma query."
                # Usa execute_natural para garantir que o Firefox abra de verdade
                # (testa o comando completo incluindo keyword de pesquisa)
                res = executor.execute_natural(f"pesquisa {query}")
                if isinstance(res, dict):
                    if res.get("success"):
                        return f"SUCESSO: Pesquisando '{query}' no Google."
                    else:
                        # Fallback direto via subprocess se o natural falhar
                        import subprocess as _sub
                        try:
                            from urllib.parse import quote as _quote
                            url = f"https://www.google.com/search?q={_quote(query)}"
                            _sub.Popen(["firefox", url], stdout=_sub.DEVNULL, stderr=_sub.DEVNULL)
                            return f"SUCESSO: Pesquisando '{query}' no Google."
                        except Exception as e:
                            try:
                                import webbrowser as _wb
                                _wb.open(url)
                                return f"SUCESSO: Pesquisando '{query}' no Google."
                            except Exception as e2:
                                return f"FALHOU: Não foi possível abrir o browser: {e2}"
                return f"SUCESSO: Pesquisando '{query}'."

            elif cmd_lower.startswith("luna-app"):
                app = cmd[8:].strip().strip('"\'')
                if not app:
                    return "FALHOU: luna-app precisa do nome do aplicativo."
                # Se for URL, abre no browser em vez de tentar abrir como app
                if app.startswith("http://") or app.startswith("https://") or app.startswith("www."):
                    url = app if app.startswith("http") else f"https://{app}"
                    res = executor.open_url(url)
                    return f"SUCESSO: Abrindo {url}" if res.get("success") else f"FALHOU: {res.get('message')}"
                res = executor.open_app(app)
                if isinstance(res, dict):
                    return f"SUCESSO: {res.get('message', 'App aberto.')}" if res.get("success") else f"FALHOU: {res.get('message', 'Erro ao abrir app.')}"
                return f"SUCESSO: {res}"

            elif cmd_lower.startswith("luna-router"):
                query = cmd[11:].strip().strip('"\'')
                if not query:
                    return "FALHOU: luna-router precisa de uma ação."
                res = executor.execute_natural(query)
                if isinstance(res, dict):
                    return f"SUCESSO: {res.get('message', 'Ação executada.')}" if res.get("success") else f"FALHOU: {res.get('message', str(res))}"
                return f"SUCESSO: {res}"

            elif cmd_lower.startswith("luna-click"):
                target = cmd[10:].strip().strip('"\'')
                if not target:
                    return "FALHOU: luna-click precisa de um alvo."
                try:
                    # Usa execute_natural que roteia para _resolve_click
                    # que usa APENAS OCR + xdotool na tela real (sem Playwright/Nightly)
                    res = executor.execute_natural(f"clica em {target}")
                    if isinstance(res, dict):
                        if res.get("success"):
                            return f"SUCESSO: {res.get('message', 'Clique executado.')}"
                        # Fallback: click_text direto via xdotool
                        fallback = executor.click_text(target)
                        if fallback.get("success"):
                            return f"SUCESSO: Clicou em '{target}'."
                        return f"FALHOU: Não encontrei '{target}' na tela via OCR."
                    return f"SUCESSO: Clique em '{target}' executado."
                except Exception as e:
                    return f"FALHOU: Erro no clique: {e}"

            elif cmd_lower.startswith("luna-browser"):
                task = cmd[12:].strip().strip('"\'')
                if not task:
                    return "FALHOU: luna-browser precisa de uma tarefa ou URL."
                try:
                    res = executor.browser_agent.run(task)
                    return f"SUCESSO: {res}"
                except Exception as e:
                    return f"FALHOU: Erro no browser agent: {e}"

            else:
                logger.warning("Prefixo não reconhecido: %s", cmd)
                return "FALHOU: Comando não reconhecido. Use: luna-spotify, luna-lights, luna-search, luna-app ou luna-router."
        elif name == "google_query":
            args = _parse_arguments(raw_args)
            service = args.get("service")
            max_results = args.get("max_results", 5)
            gm = get_google()
            if service == "calendar":
                return gm.get_calendar_events(max_results)
            elif service == "gmail":
                return gm.get_unread_emails(max_results)
            else:
                return f"FALHOU: Serviço Google desconhecido '{service}'."
        elif name == "google_send_email":
            args = _parse_arguments(raw_args)
            to = args.get("to")
            subject = args.get("subject")
            body = args.get("body")
            attachments = args.get("attachments", "")
            if not all([to, subject, body]):
                return "FALHOU: Parâmetros insuficientes para enviar email."
            return get_google().send_email(to, subject, body, attachments)
        elif name == "google_create_event":
            args = _parse_arguments(raw_args)
            summary = args.get("summary")
            start_time = args.get("start_time")
            end_time = args.get("end_time")
            description = args.get("description", "")
            location = args.get("location", "")
            attendees = args.get("attendees", "")
            if not all([summary, start_time]):
                return "FALHOU: Parâmetros insuficientes para criar evento."
            return get_google().create_calendar_event(
                summary, start_time, end_time, description, location, attendees
            )
        elif name == "google_edit_event":
            args = _parse_arguments(raw_args)
            event_id = args.get("event_id")
            if not event_id:
                return "FALHOU: event_id é obrigatório para editar evento."
            return get_google().edit_calendar_event(
                event_id, args.get("summary"), args.get("start_time"),
                args.get("end_time"), args.get("description"), args.get("location")
            )
        elif name == "google_delete_event":
            args = _parse_arguments(raw_args)
            event_id = args.get("event_id")
            if not event_id:
                return "FALHOU: event_id é obrigatório para deletar evento."
            return get_google().delete_calendar_event(event_id)
        elif name == "google_events_by_date":
            args = _parse_arguments(raw_args)
            date = args.get("date")
            if not date:
                return "FALHOU: date é obrigatória."
            return get_google().get_events_by_date(date, args.get("max_results", 20))
        elif name == "google_search_emails":
            args = _parse_arguments(raw_args)
            query = args.get("query")
            if not query:
                return "FALHOU: query de busca é obrigatória."
            return get_google().search_emails(query, args.get("max_results", 5))
        elif name == "google_read_email":
            args = _parse_arguments(raw_args)
            message_id = args.get("message_id")
            if not message_id:
                return "FALHOU: message_id é obrigatório."
            return get_google().read_email(message_id)
        elif name == "google_reply_email":
            args = _parse_arguments(raw_args)
            message_id = args.get("message_id")
            body = args.get("body")
            if not all([message_id, body]):
                return "FALHOU: message_id e body são obrigatórios."
            return get_google().reply_email(message_id, body)
        elif name == "google_forward_email":
            args = _parse_arguments(raw_args)
            message_id = args.get("message_id")
            to = args.get("to")
            if not all([message_id, to]):
                return "FALHOU: message_id e to são obrigatórios."
            return get_google().forward_email(message_id, to, args.get("extra_text", ""))
        elif name == "google_mark_read":
            args = _parse_arguments(raw_args)
            message_id = args.get("message_id")
            if not message_id:
                return "FALHOU: message_id é obrigatório."
            return get_google().mark_as_read(message_id)
        elif name == "google_delete_email":
            args = _parse_arguments(raw_args)
            message_id = args.get("message_id")
            if not message_id:
                return "FALHOU: message_id é obrigatório."
            return get_google().delete_email(message_id)
        elif name == "google_list_files":
            args = _parse_arguments(raw_args)
            return get_google().list_workspace_files(args.get("pattern", "*"))
        elif name == "google_drive_upload":
            args = _parse_arguments(raw_args)
            filepath_or_name = args.get("filepath_or_name")
            if not filepath_or_name:
                return "FALHOU: filepath_or_name é obrigatório."
            return get_google().google_drive_upload(filepath_or_name, args.get("folder_id"))
        elif name == "google_drive_list":
            args = _parse_arguments(raw_args)
            return get_google().google_drive_list(args.get("max_results", 10))
        elif name == "google_drive_search":
            args = _parse_arguments(raw_args)
            query = args.get("query")
            if not query:
                return "FALHOU: query de busca é obrigatória."
            return get_google().google_drive_search(query, args.get("max_results", 10))
        elif name == "google_drive_create_folder":
            args = _parse_arguments(raw_args)
            folder_name = args.get("folder_name")
            if not folder_name:
                return "FALHOU: folder_name é obrigatório."
            return get_google().google_drive_create_folder(folder_name, args.get("parent_id"))
        elif name == "google_drive_delete":
            args = _parse_arguments(raw_args)
            file_id = args.get("file_id")
            if not file_id:
                return "FALHOU: file_id é obrigatório."
            return get_google().google_drive_delete(file_id)
        elif name == "create_excel":
            from actions.document_services import get_doc_services
            args = _parse_arguments(raw_args)
            data = args.get("data")
            filename = args.get("filename")
            if not all([data, filename]):
                return "FALHOU: data e filename são obrigatórios."
            return get_doc_services().create_excel(data, filename)
        elif name == "create_pdf_drive":
            from actions.document_services import get_doc_services
            args = _parse_arguments(raw_args)
            content = args.get("content")
            title = args.get("title")
            if not all([content, title]):
                return "FALHOU: content e title são obrigatórios."
            return get_doc_services().create_pdf_drive(content, title)
        elif name == "read_file":
            from actions.document_services import get_doc_services
            args = _parse_arguments(raw_args)
            filepath_or_name = args.get("filepath_or_name")
            if not filepath_or_name:
                return "FALHOU: filepath_or_name é obrigatório."
            return get_doc_services().read_file(filepath_or_name)
        elif name == "save_file":
            from actions.document_services import get_doc_services
            args = _parse_arguments(raw_args)
            content = args.get("content")
            filepath_or_name = args.get("filepath_or_name")
            if not all([content, filepath_or_name]):
                return "FALHOU: content e filepath_or_name são obrigatórios."
            return get_doc_services().save_file(content, filepath_or_name)
        elif name == "get_system_status":
            from actions.system_tools import get_system_tools
            return str(get_system_tools().get_system_status())
        elif name == "get_running_processes":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            return get_system_tools().get_running_processes(args.get("limit", 10))
        elif name == "run_bash_command":
            from actions.system_tools import get_system_tools
            args = _parse_arguments(raw_args)
            command = args.get("command")
            if not command:
                return "FALHOU: command é obrigatório."
            return get_system_tools().run_bash_command(command)
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
                return "FALHOU: crew_run requires a task_description."
            return run_crew_task(task_desc)
        else:
            return f"FALHOU: Ferramenta desconhecida: {name}"
    except Exception as e:
        logger.exception("Erro interno em execute_tool_call")
        return f"FALHOU: Erro interno: {str(e)}"
    except Exception as e:
        logger.exception("Erro interno em execute_tool_call")
        return f"FALHOU: Erro interno: {str(e)}"
