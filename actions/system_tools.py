#!/usr/bin/env python3
"""
actions/system_tools.py — Ferramentas de diagnóstico e comandos do sistema operacional.
Fornece informações de hardware (CPU, RAM, Disco) e permite executar comandos bash de forma controlada.
"""
import subprocess
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List

import psutil

# Substrings bloqueadas para prevenir comandos destrutivos acidentais ou maliciosos
BANNED_SUBSTRINGS = [
    "rm -rf", "rm -r", "sudo rm", "mkfs", "dd if=",
    "shutdown", "reboot", "halt", "poweroff",
    ":(){:|:&};:", "chmod 777", "chown -R",
    "curl | sh", "wget | sh", "bash <(", "init 0", "init 6"
]

class SystemTools:
    """Ferramentas de sistema local para a Luna."""

    def __init__(self):
        pass

    def get_system_status(self) -> Dict[str, Any]:
        """
        Retorna informações detalhadas sobre o uso de CPU, Memória RAM e Disco.
        """
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count(logical=True)
            
            # RAM
            mem = psutil.virtual_memory()
            ram_total_gb = round(mem.total / (1024 ** 3), 2)
            ram_used_gb = round(mem.used / (1024 ** 3), 2)
            ram_percent = mem.percent
            
            # Disco
            usage = shutil.disk_usage("/")
            disk_total_gb = round(usage.total / (1024 ** 3), 2)
            disk_used_gb = round(usage.used / (1024 ** 3), 2)
            disk_free_gb = round(usage.free / (1024 ** 3), 2)
            disk_percent = round((usage.used / usage.total) * 100, 2)
            
            # Load Average (Linux)
            load1, load5, load15 = os.getloadavg()
            
            return {
                "success": True,
                "cpu": {
                    "usage_percent": cpu_percent,
                    "cores": cpu_count,
                    "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)]
                },
                "ram": {
                    "total_gb": ram_total_gb,
                    "used_gb": ram_used_gb,
                    "usage_percent": ram_percent
                },
                "disk": {
                    "total_gb": disk_total_gb,
                    "used_gb": disk_used_gb,
                    "free_gb": disk_free_gb,
                    "usage_percent": disk_percent
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Erro ao coletar status do sistema: {str(e)}"}

    def get_running_processes(self, limit: int = 10) -> str:
        """
        Retorna a lista dos processos que mais consomem CPU ou Memória.
        """
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    # Previne falhas se o processo sumir durante a iteração
                    info = proc.info
                    if info['cpu_percent'] is not None and info['memory_percent'] is not None:
                        processes.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Ordena por uso de CPU descrescente
            top_cpu = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:limit]
            
            result_lines = ["PID | Nome | CPU % | Memória %"]
            result_lines.append("-" * 40)
            for p in top_cpu:
                result_lines.append(f"{p['pid']} | {p['name']} | {p['cpu_percent']:.1f}% | {p['memory_percent']:.1f}%")
                
            return "\n".join(result_lines)
        except Exception as e:
            return f"FALHOU: Erro ao listar processos: {str(e)}"

    def _validate_command(self, command: str) -> Optional[str]:
        cmd_clean = command.strip()
        if not cmd_clean:
            return "FALHOU: comando vazio."
        cmd_lower = cmd_clean.lower()
        for banned in BANNED_SUBSTRINGS:
            if banned in cmd_lower:
                return f"FALHOU: O comando contém termos bloqueados por segurança ('{banned}'). Execução rejeitada."
        return None

    def run_bash_command(self, command: str, visible: bool = False) -> str:
        """
        Executa comando no shell.
        visible=True → abre terminal GNOME/zsh (usuário vê a saída).
        visible=False → headless, retorna stdout/stderr para a Luna.
        """
        err = self._validate_command(command)
        if err:
            return err

        if visible:
            from actions.gnome import open_terminal_zsh
            return open_terminal_zsh(command, title="Luna")

        try:
            res = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path.home()),
            )

            output = ""
            if res.stdout:
                output += f"--- SAÍDA (stdout) ---\n{res.stdout.strip()}\n"
            if res.stderr:
                output += f"--- ERROS (stderr) ---\n{res.stderr.strip()}\n"

            if not output:
                output = "Comando executado com sucesso (sem retorno/output)."

            return output
        except subprocess.TimeoutExpired:
            return "FALHOU: O comando expirou (timeout de 30 segundos)."
        except Exception as e:
            return f"FALHOU: Erro na execução: {str(e)}"

    def run_terminal_command(self, command: str) -> str:
        """Abre terminal visível (zsh) — atalho para run_bash_command(visible=True)."""
        return self.run_bash_command(command, visible=True)

    def kill_process(self, pid: int = 0, name: str = "") -> str:
        try:
            if pid:
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=3)
                return f"Processo {pid} ({proc.name()}) encerrado."
            if name:
                killed = 0
                for proc in psutil.process_iter(["pid", "name"]):
                    if name.lower() in proc.info["name"].lower():
                        proc.terminate()
                        killed += 1
                return f"{killed} processo(s) '{name}' encerrado(s)." if killed else f"Nenhum processo '{name}' encontrado."
            return "FALHOU: informe pid ou name."
        except psutil.NoSuchProcess:
            return f"FALHOU: PID {pid} não existe."
        except Exception as e:
            return f"FALHOU: {e}"

    def send_notification(self, title: str, message: str) -> str:
        if not shutil.which("notify-send"):
            return "FALHOU: notify-send não instalado."
        try:
            subprocess.run(["notify-send", title, message], check=True, timeout=3)
            return f"Notificação enviada: {title}"
        except Exception as e:
            return f"FALHOU: {e}"

    def get_network_status(self) -> str:
        if shutil.which("nmcli"):
            code, out = subprocess.getstatusoutput("nmcli -t -f ACTIVE,SSID,SIGNAL,SECURITY dev wifi")
            if code == 0 and out.strip():
                return "Wi-Fi:\n" + out.replace(":", " | ")
            code, out = subprocess.getstatusoutput("nmcli dev status")
            return out if code == 0 else "FALHOU: nmcli indisponível."
        if shutil.which("ip"):
            code, out = subprocess.getstatusoutput("ip -br addr")
            return out if code == 0 else "FALHOU: ip indisponível."
        return "FALHOU: ferramentas de rede não encontradas."

    def set_brightness(self, level: int) -> str:
        level = max(1, min(100, level))
        if shutil.which("brightnessctl"):
            code, out = subprocess.getstatusoutput(f"brightnessctl set {level}%")
            return f"Brilho: {level}%" if code == 0 else f"FALHOU: {out}"
        return "FALHOU: brightnessctl não instalado (pacman -S brightnessctl)."

    def take_screenshot(self, path: str = "") -> str:
        from datetime import datetime
        dest = path or str(Path.home() / "Pictures" / f"luna_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        dest = str(Path(dest).expanduser())
        Path(dest).parent.mkdir(parents=True, exist_ok=True)

        # Preferência: mss (vision) — funciona em X11 e Wayland
        try:
            from vision.screen import get_vision, SCREENSHOT_PATH
            vision = get_vision()
            if vision.capture():
                import shutil as _sh
                _sh.copy2(SCREENSHOT_PATH, dest)
                return f"Screenshot salvo: {dest}"
        except Exception:
            pass

        for cmd in [
            ["import", "-window", "root", dest],
            ["grim", dest],
            ["scrot", dest],
            ["gnome-screenshot", "-f", dest],
        ]:
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True, timeout=8)
                    return f"Screenshot salvo: {dest}"
                except Exception:
                    continue
        return "FALHOU: instale grim, scrot ou gnome-screenshot."


# Singleton helper
_system_tools_instance = None

def get_system_tools() -> SystemTools:
    global _system_tools_instance
    if _system_tools_instance is None:
        _system_tools_instance = SystemTools()
    return _system_tools_instance
