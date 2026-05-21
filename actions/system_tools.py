#!/usr/bin/env python3
"""
actions/system_tools.py — Ferramentas de diagnóstico e comandos do sistema operacional.
Fornece informações de hardware (CPU, RAM, Disco) e permite executar comandos bash de forma controlada.
"""
import subprocess
import shutil
import os
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

    def run_bash_command(self, command: str) -> str:
        """
        Executa um comando bash arbitrário de forma síncrona.
        Apenas permite comandos que não estejam na lista de bloqueios de segurança.
        """
        # Validação de segurança
        cmd_clean = command.strip()
        cmd_lower = cmd_clean.lower()
        
        for banned in BANNED_SUBSTRINGS:
            if banned in cmd_lower:
                return f"FALHOU: O comando contém termos bloqueados por segurança ('{banned}'). Execução rejeitada."
        
        try:
            res = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
                cwd="/home/pera"
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
            return "FALHOU: O comando expirou (timeout de 15 segundos)."
        except Exception as e:
            return f"FALHOU: Erro na execução: {str(e)}"


# Singleton helper
_system_tools_instance = None

def get_system_tools() -> SystemTools:
    global _system_tools_instance
    if _system_tools_instance is None:
        _system_tools_instance = SystemTools()
    return _system_tools_instance
