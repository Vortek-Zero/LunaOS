#!/bin/bash

# Terminar processos em segundo plano ao fechar/interromper
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM

echo "🚀 Iniciando o sistema completo da LUNA em um único terminal..."

# 1. Iniciar o backend Python (sem HTTPS para evitar erros de certificado no Tauri)
if [ -d ".venv" ]; then
    echo "🐍 Iniciando o backend Python..."
    export LUNA_USE_HTTPS=false
    .venv/bin/python app.py &
    BACKEND_PID=$!
else
    echo "❌ Erro: Ambiente virtual .venv não encontrado."
    exit 1
fi

# 2. Aguardar o backend iniciar na porta 5000
echo "⏳ Aguardando a API do backend ficar online..."
while ! curl -s http://localhost:5050/ > /dev/null; do
    sleep 0.5
    # Verifica se o processo do backend morreu prematuramente
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "❌ Erro: O backend falhou ao iniciar."
        exit 1
    fi
done
echo "✅ Backend online!"

# 3. Iniciar o Tauri Desktop
echo "🖥️ Iniciando a interface Tauri Desktop..."
cd luna-desktop
npm run tauri dev

# Esperar todos os processos filhos
wait
