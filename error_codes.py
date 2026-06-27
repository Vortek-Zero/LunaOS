ERROS = {
    # ── STT / Whisper / Wakeword (001-099) ──
    "STT_PYAUDIO_MISSING":     "STT-001",
    "STT_MIC_UNAVAILABLE":     "STT-002",
    "STT_RECORD_FAILED":       "STT-003",
    "STT_GROQ_FAILED":         "STT-004",
    "STT_WHISPER_FAILED":      "STT-005",
    "STT_WHISPER_LOAD_FAILED": "STT-006",
    "STT_WAKEWORD_FAILED":     "STT-007",
    "STT_WAKEWORD_LOOP":       "STT-008",

    # ── Gemini (101-199) ──
    "GEMINI_QUOTA":            "GEMINI-101",
    "GEMINI_AUTH_FAILED":      "GEMINI-102",
    "GEMINI_API_ERROR":        "GEMINI-103",
    "GEMINI_STREAM_ERROR":     "GEMINI-104",
    "GEMINI_INIT_FAILED":      "GEMINI-105",

    # ── Groq (201-299) ──
    "GROQ_RATE_LIMIT":         "GROQ-201",
    "GROQ_AUTH_FAILED":        "GROQ-202",
    "GROQ_API_ERROR":          "GROQ-203",
    "GROQ_INIT_FAILED":        "GROQ-204",

    # ── OpenRouter (301-399) ──
    "OR_NO_CREDITS":           "OR-301",
    "OR_AUTH_FAILED":          "OR-302",
    "OR_API_ERROR":            "OR-303",

    # ── GitHub Models (401-499) ──
    "GH_AUTH_FAILED":          "GH-401",
    "GH_QUOTA":                "GH-402",
    "GH_API_ERROR":            "GH-403",

    # ── Mistral (501-599) ──
    "MISTRAL_QUOTA":           "MISTRAL-501",
    "MISTRAL_AUTH_FAILED":     "MISTRAL-502",
    "MISTRAL_API_ERROR":       "MISTRAL-503",

    # ── Chutes.ai (601-699) ──
    "CHUTES_AUTH_FAILED":      "CHUTES-601",
    "CHUTES_API_ERROR":        "CHUTES-602",

    # ── Naga AI (701-799) ──
    "NAGA_AUTH_FAILED":        "NAGA-701",
    "NAGA_API_ERROR":          "NAGA-702",

    # ── Best AI (801-899) ──
    "BESTAI_AUTH_FAILED":      "BESTAI-801",
    "BESTAI_API_ERROR":        "BESTAI-802",

    # ── Ollama (901-999) ──
    "OLLAMA_UNAVAILABLE":      "OLLAMA-901",
    "OLLAMA_API_ERROR":        "OLLAMA-902",

    # ── TTS (1001-1099) ──
    "TTS_EDGE_FAILED":         "TTS-1001",
    "TTS_ELEVENLABS_FAILED":   "TTS-1002",
    "TTS_AZURE_FAILED":        "TTS-1003",
    "TTS_PYTTSX3_FAILED":      "TTS-1004",
    "TTS_KOKORO_FAILED":       "TTS-1005",
    "TTS_F5_FAILED":           "TTS-1006",
    "TTS_GOOGLECLOUD_FAILED":  "TTS-1007",
    "TTS_ALL_ENGINES_FAILED":  "TTS-1008",
    "TTS_AUDIO_DEVICE_FAILED": "TTS-1009",

    # ── Vision / OCR (1101-1199) ──
    "VIS_CAPTURE_FAILED":      "VIS-1101",
    "VIS_OCR_FAILED":          "VIS-1102",
    "VIS_GROQ_FAILED":         "VIS-1103",
    "VIS_GEMINI_FAILED":       "VIS-1104",
}

def err(key: str, detail: str = "") -> str:
    code = ERROS.get(key, "UNK-000")
    if detail:
        return f"[ERRO {code}] {detail}"
    return f"[ERRO {code}]"
