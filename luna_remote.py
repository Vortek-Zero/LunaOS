#!/usr/bin/env python3
"""
luna_remote.py — Cria um túnel para acessar a Luna de qualquer rede (3G/4G/Wi-Fi externo).
"""
import subprocess
import sys
import time
import re
import shutil
from pathlib import Path

try:
    from config import API_PORT
except ImportError:
    API_PORT = 5000

import subprocess
import sys
import time
import re
from pathlib import Path

try:
    from config import API_PORT
except ImportError:
    API_PORT = 5000

def start_tunnel():
    print("=" * 60)
    print("🌐 INICIANDO LUNA REMOTE (PINGGY)")
    print("=" * 60)
    print(f"Conectando a porta local {API_PORT} à internet...\n")
    print("\nAguardando geração do link seguro...\n")
    
    # Pinggy é a única alternativa sem cadastro que é robusta o suficiente para não dar erro 503.
    cmd_pinggy = ["ssh", "-p", "443", "-R0:localhost:" + str(API_PORT), "-o", "StrictHostKeyChecking=no", "a.pinggy.io"]
    
    try:
        process = subprocess.Popen(cmd_pinggy, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        url_found = False
        for line in process.stdout:
            line = line.strip()
            if "https://" in line and ".pinggy." in line and not url_found:
                match = re.search(r'(https://[a-zA-Z0-9.-]+\.pinggy\.[a-z]+)', line)
                if match:
                    print("\n" + "✨" * 20)
                    print("LUNA ACESSÍVEL GLOBALMENTE!")
                    print(f"👉 Link para abrir no celular: {match.group(1)}")
                    print("✨" * 20)
                    url_found = True
                    
        process.wait()
    except KeyboardInterrupt:
        print("\nLuna Remote desligado.")
    except Exception as e:
        print(f"Erro fatal no túnel: {e}")

if __name__ == "__main__":
    start_tunnel()
