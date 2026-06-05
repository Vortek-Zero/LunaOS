#!/usr/bin/env python3
"""
config.py — Configuração centralizada do sistema Luna
Tudo configurável via variáveis de ambiente para facilitar deploy separado.
"""
import os
import secrets
from pathlib import Path

# ── Diretório raiz do projeto ─────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Carrega .env local se existir ─────────────────────────────
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ── API ───────────────────────────────────────────────────────
API_HOST = os.getenv("LUNA_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("LUNA_API_PORT", "5000"))

# API Key — gera uma automática se não definida (salva em .api_key)
_API_KEY_FILE = BASE_DIR / ".api_key"

def _load_or_generate_api_key() -> str:
    """Carrega API key do env ou arquivo. Gera uma nova se não existir."""
    env_key = os.getenv("LUNA_API_KEY")
    if env_key:
        return env_key
    if _API_KEY_FILE.exists():
        return _API_KEY_FILE.read_text(encoding="utf-8").strip()
    # Gera nova key
    new_key = f"luna-{secrets.token_hex(24)}"
    _API_KEY_FILE.write_text(new_key, encoding="utf-8")
    print(f"\n🔑 Nova API key gerada e salva em {_API_KEY_FILE}")
    print(f"   Key: {new_key}\n")
    return new_key

API_KEY = _load_or_generate_api_key()

# CORS — origens permitidas (separar por vírgula no env)
CORS_ORIGINS = os.getenv("LUNA_CORS_ORIGINS", "*").split(",")

# ── Ollama / LLM ─────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"

# Modelos (Arquitetura Kitsuune)
MODELS = {
    "heavy": os.getenv("LUNA_MODEL_HEAVY", "qwen2.5-coder:7b"),
    "main":  os.getenv("LUNA_MODEL_MAIN",  "qwen2.5:3b"),
    "fast":  os.getenv("LUNA_MODEL_FAST",  "qwen2.5:0.5b-instruct-fp16"),
    "basic": os.getenv("LUNA_MODEL_BASIC", "qwen2.5:0.5b"),  # conversa rápida
}

# Timeouts por modelo (segundos)
MODEL_TIMEOUTS = {
    "fast": 30,
    "main": 120,
    "heavy": 600,
}

# ── Caminhos de dados ─────────────────────────────────────────
DATA_DIR = Path(os.getenv("LUNA_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_FILE = DATA_DIR / "memory.json"
CACHE_FILE = DATA_DIR / "cache.json"
RAG_DB_FILE = DATA_DIR / "rag_db.json"

WORKSPACE_DIR = Path(os.getenv("LUNA_WORKSPACE", "/home/pera/Luna-programming"))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

PERSONALITY_FILE = BASE_DIR / "personality.json"
APPS_FILE = BASE_DIR / "apps.json"

# ── Voice ─────────────────────────────────────────────────────
VOICE_CONFIG = {
    "voice": os.getenv("LUNA_TTS_VOICE", "pt-BR-ThalitaMultilingualNeural"),
    "rate":  os.getenv("LUNA_TTS_RATE",  "+5%"),
    "pitch": os.getenv("LUNA_TTS_PITCH", "+2Hz"),
    "volume": os.getenv("LUNA_TTS_VOLUME", "+8%"),
}

# --- MOTOR DE TTS ---
# Prioridade de motores de voz
TTS_PRIORITY = os.getenv("LUNA_TTS_PRIORITY", "google_cloud,f5,edge_tts,elevenlabs,azure,pyttsx3").split(",")

# Credenciais e vozes de outros motores
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # padrão pt-BR/Rachel
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")
AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "pt-BR-ThalitaNeural")

# Se USE_LOCAL_F5 for True, usará o clonador de voz zero-shot (F5-TTS) com seu MP3
USE_LOCAL_F5 = False
F5_REF_AUDIO = str(Path(__file__).parent / "voice" / "Vozparaokokoro.mp3")

# Se USE_LOCAL_XTTS for True (e F5 for False), tenta carregar o motor local Kokoro.
USE_LOCAL_XTTS = False
XTTS_SPEAKER_WAV = os.getenv("LUNA_XTTS_SPEAKER", str(BASE_DIR / "voice" / "samples" / "luna_base.wav"))

# STT_LANGUAGE = os.getenv("LUNA_STT_LANG", "pt-BR")
WAKEWORDS = ["ei luna", "luna", "hey luna"]

# ── Cache ─────────────────────────────────────────────────────
CACHE_TTL_HOURS = int(os.getenv("LUNA_CACHE_TTL", "24"))
CACHE_MAX_ENTRIES = int(os.getenv("LUNA_CACHE_MAX", "500"))

# ── Memory ────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("LUNA_MAX_HISTORY", "10"))
MAX_PERSISTENT_FACTS = int(os.getenv("LUNA_MAX_FACTS", "200"))
MEMORY_SAVE_DEBOUNCE_SECONDS = 5.0

# ── Arquitetura Distribuída (Orquestrador → Worker) ──────────
# Defina no .env para o PC A apontar para o PC B
WORKER_URL     = os.getenv("LUNA_WORKER_URL", "http://192.168.1.100:8000")
WORKER_API_KEY = os.getenv("LUNA_WORKER_API_KEY", "luna-changeme")

# ── Mistral AI API ──────────────────────────────────────────────
# console.mistral.ai — Modelo Principal
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

MISTRAL_MODELS = {
    "heavy": "mistral-large-latest",
    "main":  "mistral-large-latest",
    "fast":  "mistral-small-latest",
}

# ── Gemini LLM API ────────────────────────────────────────────
# aistudio.google.com/apikey — Gemini 2.5 Flash (fallback primário)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

GEMINI_MODELS = {
    "heavy":     "gemini-2.5-flash",
    "main":      "gemini-2.5-flash",
    "fast":      "gemini-2.5-flash",
    "fallback":  "gemini-2.0-flash",       # fallback 1
    "fallback2": "gemini-2.5-flash-lite",  # fallback 2
}

# ── OpenRouter LLM API ────────────────────────────────────────
# openrouter.ai — fallback 1 (quando Gemini falha, oferece modelos alternativos)
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Modelos OpenRouter — fallback com modelos top quando Gemini indisponível
OPENROUTER_MODELS = {
    "heavy":     "google/gemini-2.5-flash",  # tenta Gemini via OR primeiro
    "main":      "google/gemini-2.5-flash",
    "fast":      "google/gemini-2.0-flash-001",
    "fallback":  "meta-llama/llama-4-maverick",            # quando Gemini OR também falha
    "fallback2": "deepseek/deepseek-chat-v3-0324",
}

# ── Groq LLM API ──────────────────────────────────────────────
# console.groq.com — Whisper STT + LLM (llama3, gemma2, mixtral)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Modelos Groq (substituem Ollama quando disponível)
# REGRA: 8B = chat/conversa/planejamento (rápido, sem rate limit)
#        70B = escrita criativa, análise pesada, código complexo
GROQ_MODELS = {
    "heavy": "llama-3.3-70b-versatile",    # escrita criativa + análise pesada — reservado
    "main":  "llama-3.1-8b-instant",       # chat/conversa/planejamento — produção (rápido)
    "fast":  "llama-3.1-8b-instant",       # comandos rápidos — produção
}

# ── Tavily Search API ─────────────────────────────────────────
# app.tavily.com — substitui Wikipedia + DuckDuckGo no fact-check
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Groq Vision — modelo com suporte a imagem (403 = trocar ou deixar vazio para OCR-only)
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# ── Spotify ───────────────────────────────────────────────────
# developer.spotify.com/dashboard
SPOTIPY_CLIENT_ID     = os.getenv("SPOTIPY_CLIENT_ID", "")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET", "")
SPOTIPY_REDIRECT_URI  = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

# Propaga para o ambiente (spotipy lê via os.environ)
if SPOTIPY_CLIENT_ID:
    os.environ.setdefault("SPOTIPY_CLIENT_ID", SPOTIPY_CLIENT_ID)
if SPOTIPY_CLIENT_SECRET:
    os.environ.setdefault("SPOTIPY_CLIENT_SECRET", SPOTIPY_CLIENT_SECRET)
os.environ.setdefault("SPOTIPY_REDIRECT_URI", SPOTIPY_REDIRECT_URI)

# ── Home Assistant ────────────────────────────────────────────
# Aguardando credenciais (relé)
HOME_ASSISTANT_URL   = os.getenv("HOME_ASSISTANT_URL", "")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")

# ── Admin ─────────────────────────────────────────────────────
ADMIN_PASSWORD = os.getenv("LUNA_ADMIN_PASSWORD", "")

# WhatsApp bridge local opcional (whatsapp-web.js etc.) — sem API Meta
WHATSAPP_BRIDGE_URL = os.getenv("WHATSAPP_BRIDGE_URL", "")
