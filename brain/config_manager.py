import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "luna"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Mapa de chaves: nome amigável → variável de ambiente
API_FIELDS = {
    "groq": {
        "env": "GROQ_API_KEY",
        "label": "Groq API Key",
        "url": "https://console.groq.com/keys",
        "free": True,
        "priority": 1,
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "label": "Gemini API Key",
        "url": "https://aistudio.google.com/apikey",
        "free": True,
        "priority": 2,
    },
    "mistral": {
        "env": "MISTRAL_API_KEY",
        "label": "Mistral API Key",
        "url": "https://console.mistral.ai/api-keys",
        "free": True,
        "priority": 3,
    },
    "naga": {"env": "NAGA_API_KEY", "label": "Naga AI API Key", "url": "https://naga.ac", "free": True, "priority": 4},
    "bestai": {
        "env": "BESTAI_API_KEY",
        "label": "Best AI API Key",
        "url": "https://oaibest.com",
        "free": True,
        "priority": 5,
    },
    "github": {
        "env": "GITHUB_TOKEN",
        "label": "GitHub Token",
        "url": "https://github.com/settings/tokens",
        "free": True,
        "priority": 6,
    },
    "tavily": {
        "env": "TAVILY_API_KEY",
        "label": "Tavily Search API Key",
        "url": "https://tavily.com",
        "free": True,
        "priority": 7,
    },
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "label": "OpenRouter API Key",
        "url": "https://openrouter.ai/keys",
        "free": False,
        "priority": 8,
    },
    "chutes": {
        "env": "CHUTES_API_KEY",
        "label": "Chutes.ai API Key",
        "url": "https://chutes.ai",
        "free": False,
        "priority": 9,
    },
    "spotify_id": {
        "env": "SPOTIPY_CLIENT_ID",
        "label": "Spotify Client ID",
        "url": "https://developer.spotify.com/dashboard",
        "free": True,
        "priority": 10,
    },
    "spotify_secret": {
        "env": "SPOTIPY_CLIENT_SECRET",
        "label": "Spotify Client Secret",
        "url": "",
        "free": True,
        "priority": 11,
    },
    "ha_url": {"env": "HOME_ASSISTANT_URL", "label": "Home Assistant URL", "url": "", "free": True, "priority": 12},
    "ha_token": {
        "env": "HOME_ASSISTANT_TOKEN",
        "label": "Home Assistant Token",
        "url": "",
        "free": True,
        "priority": 13,
    },
    "elevenlabs": {
        "env": "ELEVENLABS_API_KEY",
        "label": "ElevenLabs API Key",
        "url": "https://elevenlabs.io/api-keys",
        "free": False,
        "priority": 14,
    },
}


def ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_config(data: dict):
    ensure_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    # Also update current process env so it takes effect immediately
    for key, field in API_FIELDS.items():
        val = data.get(key)
        if val:
            os.environ[field["env"]] = val
    name = data.get("name", "")
    if name:
        os.environ["LUNA_USER_NAME"] = name


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_config_into_env():
    """Carrega configuração salva no os.environ para os módulos usarem."""
    cfg = load_config()
    for key, field in API_FIELDS.items():
        val = cfg.get(key)
        if val and not os.environ.get(field["env"]):
            os.environ.setdefault(field["env"], val)
    name = cfg.get("name")
    if name:
        os.environ.setdefault("LUNA_USER_NAME", name)
    return cfg


def get_status() -> dict:
    cfg = load_config()
    configured_apis = []
    missing_apis = []
    for key, field in sorted(API_FIELDS.items(), key=lambda x: x[1]["priority"]):
        if cfg.get(key):
            configured_apis.append(field["label"])
        else:
            missing_apis.append({"key": key, **field})
    has_name = bool(cfg.get("name"))
    return {
        "configured": has_name and len(configured_apis) > 0,
        "has_name": has_name,
        "name": cfg.get("name", ""),
        "configured_apis": configured_apis,
        "missing_apis": missing_apis[:5],
        "config_file": str(CONFIG_FILE),
    }
