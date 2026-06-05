#!/usr/bin/env python3
"""
worker.py — PC B: Motor pesado da Luna (FastAPI)
Carrega luna_core, executa tudo, protegido por X-API-KEY.

Iniciar: uvicorn worker:app --host 0.0.0.0 --port 8000
"""
import signal
import time
import asyncio
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────
WORKER_API_KEY = os.getenv("WORKER_API_KEY", "")
if not WORKER_API_KEY:
    from pathlib import Path
    _key_file = Path(__file__).parent / ".api_key"
    WORKER_API_KEY = _key_file.read_text().strip() if _key_file.exists() else "luna-changeme"

WORKER_HOST = os.getenv("WORKER_HOST", "0.0.0.0")
WORKER_PORT = int(os.getenv("WORKER_PORT", "8000"))

# ── App ───────────────────────────────────────────────────────
app = FastAPI(title="Luna Worker", version="1.0.0")

_api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


def _verify_key(key: Optional[str] = Depends(_api_key_header)):
    if key != WORKER_API_KEY:
        raise HTTPException(status_code=403, detail="X-API-KEY inválida.")
    return key


# ── Lazy singleton ────────────────────────────────────────────
_luna = None


def _get_luna():
    global _luna
    if _luna is None:
        from luna_core import get_luna
        _luna = get_luna()
    return _luna


# ── Graceful shutdown ─────────────────────────────────────────
def _shutdown_handler(signum, frame):
    print(f"\n[Worker] Sinal {signum} recebido — salvando memória e encerrando...")
    global _luna
    if _luna is not None:
        try:
            _luna._memory._force_save()
            print("[Worker] Memória salva com sucesso.")
        except Exception as e:
            print(f"[Worker] Erro ao salvar memória: {e}")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)


# ── Schemas ───────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    processing_time_ms: float = 0.0


# ── Endpoints ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "luna-worker"}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(_verify_key)])
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia.")
    luna = _get_luna()
    start = time.time()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, luna.process, req.message.strip())
    return ChatResponse(
        response=response,
        processing_time_ms=round((time.time() - start) * 1000, 1),
    )


@app.get("/status", dependencies=[Depends(_verify_key)])
async def status():
    luna = _get_luna()
    # Usa apenas atributos que existem em LunaCore
    tts_ok = False
    stt_ok = False
    try:
        tts_ok = luna._tts is not None
        stt_ok = luna._stt.is_available() if luna._stt else False
    except Exception:
        pass
    return {
        "ready": not luna.processing,
        "llm_ready": luna._llm.is_ready(),
        "voice_in": stt_ok,
        "voice_out": tts_ok,
        "model": luna.get_model_mode(),
    }


@app.post("/speak", dependencies=[Depends(_verify_key)])
async def speak(req: ChatRequest):
    """Sintetiza voz no PC B (opcional — use se o TTS rodar no worker)."""
    luna = _get_luna()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, luna.speak, req.message)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    print(f"[Worker] Iniciando em {WORKER_HOST}:{WORKER_PORT}")
    print(f"[Worker] API Key: {WORKER_API_KEY[:12]}...")
    uvicorn.run(app, host=WORKER_HOST, port=WORKER_PORT, log_level="info")
