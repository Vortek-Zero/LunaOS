#!/usr/bin/env python3
"""
app.py — Headless Backend API & Worker da Luna
Inicia o servidor local FastAPI e o ouvinte de microfone para Wakeword.
"""
import time
import os
import sys

# Força codificação UTF-8 no terminal
os.environ["LC_ALL"] = "C.UTF-8"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from luna_core import get_luna
from api import start_server_thread
from actions.updater import run_update_check

def main_loop():
    print("[Luna Backend] Iniciando sistema headless...")
    try:
        luna = get_luna()
        print("[Luna Backend] Cérebro online.")
    except Exception as e:
        print(f"[Luna Backend] Erro fatal ao carregar o cérebro: {e}")
        return

    # Verifica atualizações no GitHub em background
    run_update_check()

    # Inicia o módulo de STT e o Wakeword listener nativo
    try:
        if luna.stt.is_available():
            luna.stt.enabled = True
            luna.stt.start_wakeword_listener()
            print("[Luna Backend] Wakeword listener ativo.")
    except Exception as e:
        print(f"[Luna Backend] Erro ao ligar wakeword: {e}")

    print("[Luna Backend] Entrando em modo de escuta. Pressione Ctrl+C para encerrar.")
    
    # Loop infinito que aguarda a ativação pela palavra-chave
    try:
        while True:
            if luna.stt.wake_event.is_set():
                luna.stt.wake_event.clear()
                print("[Luna Backend] Wakeword ativado! Ouvindo...")
                
                text = luna.listen()
                if text:
                    print(f"[Usuário]: {text}")
                    # Processa a intenção e gera texto
                    response = luna.process(text)
                    print(f"[Luna]: {response}")
                    # Transforma texto em áudio local via TTS
                    luna.speak(response)
                
                # Reativa o ouvinte
                try:
                    if luna.voice_input_enabled:
                        luna.stt.start_wakeword_listener()
                except Exception:
                    pass
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[Luna Backend] Desligando graciosamente...")

if __name__ == "__main__":
    if "--test-update" in sys.argv:
        from actions.updater import test_notification
        print(test_notification())
        sys.exit(0)

    # 1. Inicia o servidor da API (FastAPI) em background
    start_server_thread()
    # 2. Mantém o loop principal travado aguardando eventos de voz
    main_loop()
