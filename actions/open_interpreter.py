"""Open Interpreter — agente autônomo que escreve e executa código para interagir
com qualquer aplicativo no sistema. Integrado ao conselho multi-modelo da Luna.
Usa o próprio cascade LLM da Luna em vez do pacote open-interpreter (incompatível com Python 3.13+).
"""

import json
import sys
import textwrap
from pathlib import Path

MAX_ITERATIONS = 8
SAFETY_BLOCKED_COMMANDS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "chmod 777 /",
    "> /dev/sda",
    "wget http",
    "curl http",
    "chown",
]


def _is_safe(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower().strip()
    for blocked in SAFETY_BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Comando bloqueado por segurança: {blocked}"
    if "sudo" in cmd_lower and ("rm" in cmd_lower or "apt" not in cmd_lower):
        return False, "Uso de sudo restrito a apt"
    return True, ""


def _run_code(code: str, language: str) -> dict:
    if language == "python":
        try:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                f.flush()
                fname = f.name

            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
            )
            Path(fname).unlink(missing_ok=True)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "code": code,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Timeout de 30s excedido", "code": code}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "code": code}
    elif language == "bash":
        safe, msg = _is_safe(code)
        if not safe:
            return {"success": False, "stdout": "", "stderr": msg, "code": code}
        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "code": code,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Timeout de 30s excedido", "code": code}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "code": code}
    return {"success": False, "stdout": "", "stderr": f"Linguagem não suportada: {language}", "code": code}


def open_interpreter_run(task: str) -> str:
    """Executa uma tarefa autônoma: LLM gera código → executa → itera."""
    from brain.llm import get_llm

    llm = get_llm()
    system_prompt = textwrap.dedent("""\
    Você é um engenheiro de software especializado em automação de sistemas.
    Dado um objetivo do usuário, você DEVE:
    1. Escolher a linguagem (python ou bash)
    2. Escrever código COMPLETO e EXECUTÁVEL
    3. Retornar APENAS JSON: {"language": "python|bash", "code": "..."}

    Regras:
    - Python para interagir com APIs, manipular arquivos, GUI (pyautogui, xdotool)
    - Bash para comandos de terminal, pipe, grep, sistema
    - NUNCA use sudo ou comandos destrutivos
    - Use xdotool, wmctrl para controlar janelas
    - Use xdg-open ou subprocess.Popen para abrir apps
    - Código deve ser AUTO-SUFICIENTE (imports inclusos)
    """)

    history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Objetivo: {task}"},
    ]

    for i in range(MAX_ITERATIONS):
        raw = llm.generate(
            messages=history,
            task_type="utility",
            model="main",
        )
        content = raw.get("message", {}).get("content", "") if isinstance(raw, dict) else str(raw or "")

        try:
            parsed = json.loads(content)
            language = parsed.get("language", "python")
            code = parsed.get("code", "")
        except (json.JSONDecodeError, TypeError):
            history.append({"role": "assistant", "content": content})
            history.append(
                {"role": "user", "content": 'ERRO: Responda APENAS em JSON: {"language": "python|bash", "code": "..."}'}
            )
            continue

        if not code:
            return "FALHOU: Nenhum código foi gerado."

        print(f"[OpenInterpreter] Passo {i + 1}: executando {language}")
        result = _run_code(code, language)

        if result["success"]:
            output = result["stdout"].strip()
            output_msg = f"Saída:\n{output}" if output else "Executado com sucesso (sem saída)."
            if result["stderr"]:
                output_msg += f"\nStderr:\n{result['stderr']}"
            history.append({"role": "assistant", "content": json.dumps(parsed)})
            history.append(
                {
                    "role": "user",
                    "content": f"{output_msg}\n\nO objetivo foi cumprido? Responda SIM ou continue com mais código.",
                }
            )
        else:
            error = result["stderr"]
            history.append({"role": "assistant", "content": json.dumps(parsed)})
            history.append(
                {"role": "user", "content": f"Erro na execução:\n{error}\n\nCorrija o código e tente novamente."}
            )

        raw2 = llm.generate(
            messages=history,
            task_type="utility",
            model="main",
        )
        content2 = raw2.get("message", {}).get("content", "") if isinstance(raw2, dict) else str(raw2 or "")
        if "SIM" in content2.upper():
            history.append({"role": "assistant", "content": content2})
            break

    return f"SUCESSO: Tarefa concluída em {i + 1} passos.\n{result['stdout'][:500]}"
