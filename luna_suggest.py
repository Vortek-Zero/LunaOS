#!/usr/bin/env python3
"""Sugere correção ou otimização para comandos do terminal."""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.CRITICAL)


def suggest(failed_command: str, error_output: str = "") -> str:
    old_out = os.dup(1)
    old_err = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)

    try:
        from luna_core import get_luna

        luna = get_luna()
        response = luna.process(
            f"O comando abaixo falhou no terminal. "
            f"Explique o erro em UMA linha e sugira o comando correto. "
            f"Seja ultra conciso, sem saudação.\n\n"
            f"Comando: {failed_command}\n"
            f"Erro: {error_output[:300]}"
        ).strip()
    finally:
        os.dup2(old_out, 1)
        os.dup2(old_err, 2)
        os.close(devnull)
        os.close(old_out)
        os.close(old_err)

    return response


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read().strip()
    print(suggest(cmd))
