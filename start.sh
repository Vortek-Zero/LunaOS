#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
#  start.sh — Inicializa a Luna automaticamente via uv
# ─────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Mata processo anterior na porta 5050 se existir
_PID=$(lsof -ti:5050 2>/dev/null || true)
if [ -n "$_PID" ]; then
    echo "⏳ Porta 5050 ocupada (PID $_PID) — encerrando..."
    kill "$_PID" 2>/dev/null || true
    sleep 1
    # Força kill se ainda estiver vivo
    kill -9 "$_PID" 2>/dev/null || true
fi

# Prefere uv; se não existir, ativa venv manual
if command -v uv &>/dev/null; then
    echo "🌙 Iniciando Luna via uv..."
    echo "   Python: $(uv run python3 --version 2>&1)"
    echo ""
    exec uv run python3 app.py "$@"
elif [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "🌙 Iniciando Luna..."
    echo "   Python: $(python3 --version 2>&1)"
    echo "   Venv:   ${VIRTUAL_ENV}"
    echo ""
    exec python3 app.py "$@"
else
    echo "🌙 Iniciando Luna (Python direto)..."
    echo "   Python: $(python3 --version 2>&1)"
    echo ""
    exec python3 app.py "$@"
fi
