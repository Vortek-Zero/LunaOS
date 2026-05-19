#!/usr/bin/env python3
import json
import re
import logging

logger = logging.getLogger("luna.agent_tools")

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
        return json.loads(raw_arguments)
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

        if name != "run_luna_command":
            return f"FALHOU: Ferramenta desconhecida: {name}"

        args = _parse_arguments(raw_args)
        cmd = args.get("command", "").strip()

        if not cmd:
            return "FALHOU: Comando vazio recebido."

        if _is_blocked(cmd):
            logger.warning("Comando bloqueado por segurança: %s", cmd)
            return f"FALHOU: Comando bloqueado por política de segurança."

        logger.info("Executando: %s", cmd)
        cmd_lower = cmd.lower()

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

    except Exception as e:
        logger.exception("Erro interno em execute_tool_call")
        return f"FALHOU: Erro interno: {str(e)}"
