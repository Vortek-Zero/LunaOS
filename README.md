<div align="center">

<img src="newlogoluna.png" alt="Luna" width="140"/>

# Luna

**Assistente pessoal autônoma com IA — feita para viver no seu computador, não na nuvem.**

[![Python](https://img.shields.io/badge/Python-3.10+-8B5CF6?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-8B5CF6?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tauri](https://img.shields.io/badge/Tauri-2.0-8B5CF6?style=flat-square&logo=tauri&logoColor=white)](https://tauri.app/)
[![Gemini](https://img.shields.io/badge/Gemini-API-8B5CF6?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/)
[![Groq](https://img.shields.io/badge/Groq-API-8B5CF6?style=flat-square&logo=groq&logoColor=white)](https://groq.com/)
[![Linux](https://img.shields.io/badge/Linux-Arch%20%2F%20Ubuntu-8B5CF6?style=flat-square&logo=linux&logoColor=white)](https://archlinux.org/)
[![License](https://img.shields.io/badge/Licença-MIT-8B5CF6?style=flat-square)](LICENSE)

</div>

---

Luna é uma assistente pessoal que roda localmente, controla seu sistema operacional, gerencia agenda e e-mail, acende a luz da sua sala, pesquisa na web e escreve código — tudo em português, tudo via conversa natural.

Não é um wrapper de ChatGPT. É um agente autônomo com loop ReAct, memória persistente, 60+ ferramentas reais e personalidade configurável.

---

## O que a Luna faz de verdade

### 🖥️ Automação de Desktop
- Abre, fecha e controla aplicativos
- Clica em elementos na tela por descrição (OCR + visão)
- Digita texto, ativa atalhos, controla janelas
- Tira screenshots e descreve o que está na tela
- Executa comandos no terminal (Bash/shell)
- Mata processos pelo nome ou PID

### 🧠 Agente Autônomo (Loop ReAct)
- Encadeia múltiplas ferramentas para completar tarefas complexas
- Planeja e executa sem precisar de confirmação a cada passo
- Cascade de 8 provedores de LLM com fallback automático (Gemini → Groq → Mistral → ...)
- Loop Guard para detectar e quebrar ciclos infinitos

### 📅 Google Workspace
- Gmail: ler, enviar, responder, encaminhar, buscar e-mails
- Calendar: criar, editar, deletar eventos, ver agenda do dia
- Google Drive: subir, listar, buscar e organizar arquivos

### 🔊 Voz
- TTS em português via Edge TTS (voz natural, sem custo)
- STT com Faster Whisper — reconhecimento local offline
- Wakeword para ativação por voz
- Modo voz com respostas curtas e naturais

### 🏠 Casa Inteligente
- Controla luzes via Tuya (liga/desliga/intensidade)
- Gerencia lista de compras, notas e lembretes
- Briefing diário ao acordar (agenda + clima + e-mails pendentes)

### 👁️ Visão Computacional
- Captura de tela com `mss`
- OCR com Tesseract para ler conteúdo na tela
- Análise de tela com Gemini Vision como fallback

### 🎵 Entretenimento
- Controla Spotify (tocar, pausar, próxima, anterior)
- Controle de volume e mídia do sistema

### 💬 Memória e Contexto
- Memória de curto prazo (histórico da conversa)
- Memória de longo prazo com fatos do usuário (SQLite)
- Cache L1 (RAM) + L2 (disco) para respostas repetidas
- Personalidade e perfil de usuário configuráveis via JSON

### 🛠️ Código e Arquivos
- Escreve arquivos em qualquer linguagem (`write_code`)
- Cria projetos completos com estrutura de diretórios
- Lê, edita e organiza arquivos locais
- Modo código com streaming de output

---

## Arquitetura

```
Luna/
├── luna_core.py          # Cérebro central — Loop ReAct, orquestração
├── api.py                # API FastAPI (REST + SSE para streaming)
├── config.py             # Configuração centralizada
│
├── brain/
│   ├── llm.py            # Cascade de provedores (Gemini, Groq, Mistral...)
│   ├── agent_tools.py    # 60+ ferramentas tipadas para o LLM
│   ├── memory.py         # Memória persistente (fatos + histórico)
│   ├── loop_guard.py     # Detecção de ciclos infinitos
│   ├── safety.py         # Filtros de segurança
│   └── daily_routine.py  # Worker proativo + rotinas diárias
│
├── voice/
│   ├── tts.py            # Text-to-Speech (Edge TTS + pyttsx3)
│   └── stt.py            # Speech-to-Text (Faster Whisper)
│
├── actions/
│   ├── executor.py       # Execução de ações no sistema
│   ├── ui.py             # Automação de interface (xdotool/ydotool)
│   ├── image_gen.py      # Geração de imagens (Gemini Imagen)
│   └── writer.py         # Modo escrita criativa
│
├── vision/
│   └── screen.py         # Captura de tela + OCR
│
├── performance_cache.py  # Cache L1/L2 com TTL e LRU
├── output_parser.py      # Parser de respostas do LLM
│
└── luna-desktop/         # App desktop (Tauri + frontend web)
```

---

## Requisitos

### Sistema (testado em Arch Linux)
```bash
# Dependências de sistema
sudo pacman -S tesseract tesseract-data-por wmctrl xdotool gio playerctl

# Wayland (opcional, para automação de UI)
sudo pacman -S ydotool wtype
systemctl --user enable --now ydotoold
```

### Python 3.10+
```bash
git clone https://github.com/milogol2822/LunaOS.git
cd LunaOS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Instale o Playwright para automação de browser
playwright install chromium
```

---

## Configuração

```bash
# 1. Copie o arquivo de exemplo
cp .env.example .env

# 2. Edite o .env com suas chaves
nano .env
```

Chaves necessárias no `.env`:

| Variável | Para quê | Gratuito? |
|---|---|---|
| `GEMINI_API_KEY` | LLM principal + visão + imagens | ✅ Sim |
| `GROQ_API_KEY` | LLM rápido (fallback) | ✅ Sim |
| `GOOGLE_CLIENT_ID` / `SECRET` | Gmail + Calendar + Drive | ✅ Sim |
| `TUYA_CLIENT_ID` / `SECRET` | Luzes inteligentes | ✅ Sim |
| `SPOTIFY_CLIENT_ID` / `SECRET` | Controle do Spotify | ✅ Sim |

---

## Como rodar

```bash
# Inicia o servidor da Luna
python api.py

# A interface web fica disponível em:
# http://localhost:8000
```

Para rodar o app desktop (Tauri):
```bash
cd luna-desktop
npm install
npm run tauri dev
```

---

## Modos de operação

| Modo | Ativa com | Comportamento |
|---|---|---|
| **Normal** | padrão | Conversa + ações no sistema |
| **Código** | `/code` | Escreve código com preview ao vivo |
| **Escrita** | `/write` | Modo escritora — texto narrativo |
| **Voz** | `/voice` | Respostas curtas e naturais para TTS |
| **Jogo** | `/joy` | Companheira de jogo — reações expressivas |

---

## Personalidade

A personalidade da Luna é configurável em `config/personality.json` — sem mexer em código.

```json
{
  "identity": { "name": "Luna", "age": 28 },
  "personality": ["sincera", "empática", "madura", "direta", "proativa"],
  "response_style": {
    "principles": ["resposta direta primeiro", "parágrafos curtos"],
    "rules": {
      "never": ["textões corridos", "respostas vagas", "excesso de formalidade"]
    }
  }
}
```

---

## Limitações conhecidas

- **WhatsApp UI** — frágil; quebra quando o layout do app muda
- **ydotool** — requer daemon `ydotoold` ativo no Wayland
- **Conversas longas** — contexto truncado após ~20 trocas (memória compacta em desenvolvimento)
- **Sem LLM offline** — todas as ações dependem de API externa (intencional por ora)
- **Linux only** — automação de UI usa xdotool/ydotool

---

## Stack

| Camada | Tecnologia |
|---|---|
| LLM | Gemini 2.0 Flash, Groq (Llama), Mistral |
| API | FastAPI + Uvicorn + SSE |
| Desktop | Tauri 2.0 |
| Voz | Faster Whisper (STT) + Edge TTS (TTS) |
| Visão | mss + Tesseract OCR + Gemini Vision |
| Casa Inteligente | Tuya IoT |
| Agenda/Email | Google APIs (Gmail, Calendar, Drive) |
| Cache | L1 RAM + L2 JSON com TTL e LRU |
| Memória | SQLite (histórico) + JSON (fatos) |

---

## Licença

MIT © [milogol2822](https://github.com/milogol2822)

---

<div align="center">
<sub>Feito com 🌙 por Pera</sub>
</div>
