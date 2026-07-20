import json
import os
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "data" / "settings.json"


def _load() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get(key: str, default=None):
    return _load().get(key, default)


def set(key: str, value) -> None:
    data = _load()
    data[key] = value
    _save(data)


def apply_all():
    """Aplica settings salvas nas configs em memória (chamar ANTES de importar brain.llm)."""
    data = _load()
    if not data:
        return

    import config as _cfg

    llm = data.get("llm_cascade")
    if llm:
        _cfg.CASCADE_ORDER = [p.strip() for p in llm if p.strip()]

    img = data.get("image_cascade")
    if img:
        _cfg.IMAGE_CASCADE_ORDER = [p.strip() for p in img if p.strip()]

    tts_provider = data.get("tts_provider")
    if tts_provider:
        os.environ["LUNA_TTS_PRIORITY"] = tts_provider
        _cfg.TTS_PRIORITY = tts_provider.split(",")

    tts_voice = data.get("tts_voice")
    if tts_voice:
        os.environ["LUNA_TTS_VOICE"] = tts_voice
        _cfg.VOICE_CONFIG["voice"] = tts_voice

    crew = data.get("crew_enabled")
    if crew is not None:
        _cfg.CREW_ENABLED = bool(crew)
        os.environ["CREW_ENABLED"] = str(crew).lower()

    wm = data.get("writing_model")
    if wm:
        os.environ["LUNA_MODEL_WRITING"] = wm
