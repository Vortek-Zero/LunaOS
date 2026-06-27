#!/usr/bin/env python3
"""
api.py — API REST FastAPI do sistema Luna
Endpoints completos com autenticação por API key.
Preparado para separação: frontend web pode rodar em outro servidor.
"""
import time
import asyncio
import json
import hashlib
import logging
import logging as _logging
import secrets as _secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor

import config

_llm_executor = _ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm")
_whisper_model = None

_logging.basicConfig(level=_logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = _logging.getLogger("luna.api")

# ── App FastAPI ───────────────────────────────────────────────

app = FastAPI(
    title="Luna AI API",
    description="API do agente autônomo Luna — Arquitetura Kitsuune",
    version="2.0.0",
)

# CORS
allowed = list(config.CORS_ORIGINS)
if "*" in allowed:
    allowed = ["*"]
    allow_credentials = False
else:
    allow_credentials = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiting ─────────────────────────────────────────────
import time as _rate_time

_rate_limit_data: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 30  # requests per minute per IP

def _check_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = _rate_time.time()
    window = 60.0
    timestamps = _rate_limit_data[client_ip]
    # Remove old entries
    while timestamps and now - timestamps[0] > window:
        timestamps.pop(0)
    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Muitas requisições. Aguarde um momento.")
    timestamps.append(now)

# ── Autenticação API Key ──────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(request: Request, api_key: Optional[str] = Depends(API_KEY_HEADER)):
    # Conexões locais (Tauri Desktop, frontend local) não precisam de chave
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return api_key or "local"
    if not api_key or api_key != config.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="API key inválida ou ausente. Use header X-API-Key."
        )
    return api_key


# ── Usuários (cadastro por dispositivo) ──────────────────────

_USERS_FILE = Path(__file__).parent / "data" / "users.json"

def _load_users() -> dict:
    try:
        if _USERS_FILE.exists():
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_users(users: dict) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

_TOKEN_SALT = _secrets.token_hex(8)  # random salt at module level

def _token_for(username: str, device_id: str) -> str:
    raw = f"{username}:{device_id}:{config.API_KEY}:{_TOKEN_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()

def _verify_user_token(token: str) -> Optional[str]:
    """Retorna username se token válido, None caso contrário."""
    users = _load_users()
    for username, data in users.items():
        if token in data.get("tokens", []):
            return username
    return None


# ── Lazy singleton da Luna ────────────────────────────────────

_luna = None


def get_luna():
    """Importa e retorna singleton da Luna (lazy — só carrega quando API é chamada)."""
    global _luna
    if _luna is None:
        from luna_core import get_luna as _get_luna
        _luna = _get_luna()
    return _luna


# ── Modelos Pydantic ──────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    cached: bool = False
    processing_time_ms: float = 0

class FactRequest(BaseModel):
    fact: str
    category: str = "geral"
    importance: float = 0.5

class StatusResponse(BaseModel):
    ready: bool
    voice_in: bool
    voice_out: bool
    llm_ready: bool
    cache_entries: int
    memory_facts: int
    memory_history: int
    writing_model: str
    processing: bool = False
    current_action: str = ""

class ModelRequest(BaseModel):
    mode: str  # "medium" or "high"

class SessionRequest(BaseModel):
    session_id: str
    title: str = ""

class RenameSessionRequest(BaseModel):
    session_id: str
    new_title: str

class MediaRequest(BaseModel):
    action: str   # play, pause, next, prev, stop, volume_up, volume_down, mute
    value: int = 10  # para volume

class TimerRequest(BaseModel):
    seconds: int
    name: str = "timer"

class NoteRequest(BaseModel):
    text: str

class ReminderRequest(BaseModel):
    text: str = ""          # linguagem natural (voz/chat)
    message: str = ""       # nome/mensagem do lembrete
    date: str = ""          # DD/MM ou DD/MM/YYYY
    hour: int = -1          # hora (0-23)
    minute: int = 0         # minuto (0-59)

class RegisterRequest(BaseModel):
    username: str
    api_key: str   # usuário precisa saber a API key para se cadastrar
    device_id: str # ID único do dispositivo (gerado no frontend)

class LoginRequest(BaseModel):
    username: str
    api_key: str
    device_id: str


# ── Endpoints de autenticação de usuário ─────────────────────

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Cadastra usuário. Requer a API key do sistema."""
    if req.api_key != config.API_KEY:
        raise HTTPException(status_code=403, detail="API key inválida.")
    username = req.username.strip().lower()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="Nome de usuário inválido.")
    users = _load_users()
    if username in users:
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    token = _token_for(username, req.device_id)
    users[username] = {"tokens": [token], "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save_users(users)
    return {"success": True, "token": token, "username": username}


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login — valida API key e retorna token do dispositivo."""
    if req.api_key != config.API_KEY:
        raise HTTPException(status_code=403, detail="API key inválida.")
    username = req.username.strip().lower()
    users = _load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    token = _token_for(username, req.device_id)
    # Adiciona token se ainda não existir (novo dispositivo do mesmo usuário)
    if token not in users[username]["tokens"]:
        users[username]["tokens"].append(token)
        _save_users(users)
    return {"success": True, "token": token, "username": username}


@app.get("/api/auth/verify")
async def verify_token(request: Request):
    """Verifica se o token do dispositivo ainda é válido."""
    token = request.headers.get("X-User-Token", "")
    username = _verify_user_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token inválido ou conta removida.")
    return {"valid": True, "username": username}


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Remove o token deste dispositivo."""
    token = request.headers.get("X-User-Token", "")
    users = _load_users()
    changed = False
    for data in users.values():
        if token in data.get("tokens", []):
            data["tokens"].remove(token)
            changed = True
            break
    if changed:
        _save_users(users)
    return {"success": True}


# ── Helpers de auth por token de usuário ─────────────────────

def _require_user(request: Request) -> str:
    token = request.headers.get("X-User-Token", "")
    username = _verify_user_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token inválido ou conta removida.")
    return username

ADMIN_PASSWORD = config.ADMIN_PASSWORD

def _require_admin(request: Request) -> str:
    username = _require_user(request)
    admin_pass = request.headers.get("X-Admin-Pass", "")
    if not admin_pass or admin_pass != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")
    return username


_ADMIN_AUDIT_LOG = Path(__file__).parent / "data" / "admin_audit.log"

def _log_admin_action(username: str, action: str, detail: str = ""):
    _ADMIN_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    msg = f"[{ts}] {username} | {action}"
    if detail:
        msg += f" | {detail}"
    with open(_ADMIN_AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ── Central de Controle — Luzes ───────────────────────────────

class LightRequest(BaseModel):
    state: bool  # True = ligar, False = desligar

@app.post("/api/control/lights")
async def control_lights(req: LightRequest, _key: str = Depends(verify_api_key)):
    from actions.lights import _set_light
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _set_light, req.state)
    return {"result": result}

@app.get("/api/control/lights/status")
async def lights_status(_key: str = Depends(verify_api_key)):
    from actions.lights import _get_device, _TUYA_OK
    if not _TUYA_OK:
        return {"on": None, "error": "tinytuya não instalado"}
    try:
        dev = _get_device()
        status = dev.status()
        on = status.get("dps", {}).get("1", None)
        return {"on": on}
    except Exception as e:
        return {"on": None, "error": str(e)}


# ── Agendamentos de luz ───────────────────────────────────────

class ScheduleRequest(BaseModel):
    hour: int
    minute: int
    state: bool
    days: list = None   # None = todos os dias
    label: str = ""

@app.get("/api/control/lights/schedules")
async def list_schedules(_key: str = Depends(verify_api_key)):
    from actions.light_scheduler import get_light_scheduler
    return {"schedules": get_light_scheduler().list_schedules()}

@app.post("/api/control/lights/schedules")
async def add_schedule(req: ScheduleRequest, _key: str = Depends(verify_api_key)):
    from actions.light_scheduler import get_light_scheduler
    result = get_light_scheduler().add(req.hour, req.minute, req.state, req.days, req.label)
    return {"success": True, "result": result}

@app.delete("/api/control/lights/schedules/{sid}")
async def remove_schedule(sid: str, _key: str = Depends(verify_api_key)):
    from actions.light_scheduler import get_light_scheduler
    ok = get_light_scheduler().remove(sid)
    return {"success": ok}

@app.patch("/api/control/lights/schedules/{sid}/toggle")
async def toggle_schedule(sid: str, _key: str = Depends(verify_api_key)):
    from actions.light_scheduler import get_light_scheduler
    msg = get_light_scheduler().toggle(sid)
    return {"success": bool(msg), "result": msg}


# ── Central de Controle — Processos ──────────────────────────

@app.get("/api/control/processes")
async def list_processes(_key: str = Depends(verify_api_key)):
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "cpu": round(p.info["cpu_percent"] or 0, 1),
                    "mem": round(p.info["memory_percent"] or 0, 1),
                    "status": p.info["status"],
                })
            except Exception:
                pass
        procs.sort(key=lambda x: x["mem"], reverse=True)
        return {"processes": procs[:40]}
    except ImportError:
        return {"error": "psutil não instalado"}

class PidRequest(BaseModel):
    pid: int

@app.post("/api/control/processes/kill")
async def kill_process(req: PidRequest, _key: str = Depends(verify_api_key)):
    try:
        import psutil, signal as _sig
        p = psutil.Process(req.pid)
        name = p.name()
        p.send_signal(_sig.SIGTERM)
        return {"success": True, "message": f"SIGTERM enviado para '{name}' (PID {req.pid})"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Central de Controle — Notas/Lembretes (leitura rápida) ───

@app.get("/api/control/summary")
async def control_summary(_key: str = Depends(verify_api_key)):
    """Resumo rápido: notas + lembretes + timers."""
    ex = get_luna()._executor
    notes = [n["text"] for n in ex.notes._notes]
    reminders = ex.reminders.list_reminders()
    timers = ex.timer.status()
    return {"notes": notes, "reminders": reminders, "timers": timers}


# ── Admin — Dispositivos conectados ──────────────────────────

@app.get("/api/admin/devices")
async def admin_devices(request: Request):
    """Lista dispositivos (usuários) conectados. Apenas admin."""
    username = _require_admin(request)
    _log_admin_action(username, "admin_devices", "Listou dispositivos conectados")
    users = _load_users()
    result = []
    for username, data in users.items():
        result.append({
            "username": username,
            "devices": len(data.get("tokens", [])),
            "created": data.get("created", ""),
        })
    return {"devices": result}

@app.delete("/api/admin/devices/{username}")
async def admin_remove_device(username: str, request: Request):
    """Remove conta de usuário. Apenas admin."""
    admin_user = _require_admin(request)
    _log_admin_action(admin_user, "admin_remove_device", f"Removeu conta: {username}")
    users = _load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    del users[username]
    _save_users(users)
    return {"success": True}

@app.delete("/api/system/reset")
async def reset_system(request: Request, _key: str = Depends(verify_api_key)):
    """Limpeza total: reseta memória, cache e arquivos de estado."""
    admin_user = _require_admin(request)
    _log_admin_action(admin_user, "reset_system", "Resetou o sistema")
    luna = get_luna()
    # Limpa memória RAG/Fatos
    if hasattr(luna._memory, 'rag'):
        luna._memory.rag.reset_collections()
    # Limpa arquivos de cache e histórico
    data_dir = Path(__file__).parent / "data"
    files_to_clear = ["chat_history.db", "memory.json", "notes.json", "reminders.json", "shopping_list.json"]
    for f in files_to_clear:
        path = data_dir / f
        if path.exists():
            if path.suffix == '.db':
                import sqlite3
                conn = sqlite3.connect(path)
                conn.execute("DELETE FROM messages")
                conn.commit()
                conn.close()
            else:
                path.write_text(json.dumps([]))
    return {"success": True, "message": "Sistema resetado com sucesso."}


# ── Endpoints públicos (sem auth) ─────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Serve a interface web."""
    index_path = Path(__file__).parent / "web" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Luna API online. Interface web não encontrada."}


@app.get("/api/health")
async def health():
    """Health check simples — não requer API key."""
    return {
        "status": "ok",
        "service": "Luna AI",
        "version": "2.0.0",
        "timestamp": time.time(),
    }


# ── Endpoints autenticados ────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, req: ChatRequest, _key: str = Depends(verify_api_key)):
    """Envia mensagem para a Luna e recebe resposta."""
    _check_rate_limit(request)
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")

    luna = get_luna()

    start = time.time()

    # Roda processamento em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(_llm_executor, luna.process, message)

    elapsed_ms = (time.time() - start) * 1000

    return ChatResponse(
        response=response,
        cached=getattr(luna, '_last_was_cached', False),
        processing_time_ms=round(elapsed_ms, 1),
    )


# ── Coding Mode ───────────────────────────────────────────────

# Memória de contexto por sessão de coding (em RAM, não persiste)
_code_sessions: dict[str, list[dict]] = {}

class CodeChatRequest(BaseModel):
    message: str
    current_code: str = ""
    session_id: str = "default"

class CodeChatResponse(BaseModel):
    code: str          # HTML completo gerado/atualizado
    explanation: str   # resposta em linguagem natural
    processing_time_ms: float = 0.0

@app.post("/api/code/chat", response_model=CodeChatResponse)
async def code_chat(req: CodeChatRequest, _key: str = Depends(verify_api_key)):
    """Chat especializado em geração/correção de HTML+JS+CSS ao vivo."""
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")

    luna = get_luna()
    sid = req.session_id or "default"
    history = _code_sessions.setdefault(sid, [])

    # Monta histórico resumido (últimas 4 trocas)
    hist_text = ""
    for h in history[-4:]:
        hist_text += f"Usuário: {h['user']}\nLuna: {h['explanation']}\n\n"

    has_code = bool(req.current_code.strip())
    code_ctx = f"\n\nCódigo atual no editor:\n```html\n{req.current_code[:8000]}\n```" if has_code else ""

    prompt = f"""Você é um especialista em desenvolvimento web (HTML, CSS, JavaScript).
Sua tarefa é gerar ou modificar código HTML completo e funcional.

REGRAS ABSOLUTAS:
1. Responda SEMPRE em JSON válido com exatamente dois campos: "code" e "explanation"
2. "code": o HTML COMPLETO (<!DOCTYPE html>...) pronto para rodar no browser. NUNCA omita partes.
3. "explanation": resposta curta e natural em português explicando o que foi feito (máx 2 frases).
4. Se o usuário reportar um erro, corrija-o no código e explique a correção.
5. CSS e JS devem ser internos (dentro do próprio HTML) a menos que o usuário peça externo.
6. NUNCA use markdown (```) dentro dos campos JSON.

{f"Histórico recente:{chr(10)}{hist_text}" if hist_text else ""}
{code_ctx}

Pedido do usuário: {message}

Responda APENAS com JSON válido:
{{"code": "<!DOCTYPE html>...", "explanation": "..."}}"""

    start = time.time()
    loop = asyncio.get_event_loop()

    from brain.llm import get_llm, GROQ_MODELS, MODELS
    llm = get_llm()
    raw = await loop.run_in_executor(
        None,
        lambda: llm.generate(prompt, task_type="coding", model=GROQ_MODELS["heavy"] if llm._use_groq("coding") else MODELS["heavy"])
    )

    elapsed_ms = (time.time() - start) * 1000

    # Parseia resposta
    code_out = req.current_code  # fallback: mantém código atual
    explanation = str(raw)

    import re as _re
    # Tenta JSON direto
    try:
        # Remove markdown wrapper se houver
        clean = _re.sub(r'^```(?:json)?\s*|\s*```$', '', str(raw).strip(), flags=_re.MULTILINE)
        # Extrai o JSON
        m = _re.search(r'\{.*\}', clean, _re.DOTALL)
        if m:
            data = json.loads(m.group())
            code_out = data.get("code", code_out).strip()
            explanation = data.get("explanation", explanation).strip()
    except Exception:
        # Se falhou, tenta extrair o HTML diretamente
        m_html = _re.search(r'(<!DOCTYPE html>.*)', str(raw), _re.DOTALL | _re.IGNORECASE)
        if m_html:
            code_out = m_html.group(1).strip()
            explanation = "Código gerado."

    # Salva no histórico
    history.append({"user": message, "explanation": explanation})
    if len(history) > 20:
        _code_sessions[sid] = history[-20:]

    return CodeChatResponse(
        code=code_out,
        explanation=explanation,
        processing_time_ms=round(elapsed_ms, 1),
    )

@app.delete("/api/code/session/{session_id}")
async def clear_code_session(session_id: str, _key: str = Depends(verify_api_key)):
    """Limpa memória da sessão de coding."""
    _code_sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/api/status", response_model=StatusResponse)
async def status(_key: str = Depends(verify_api_key)):
    """Estado completo do sistema."""
    luna = get_luna()

    cache_entries = 0
    if hasattr(luna, '_cache') and luna._cache:
        cache_entries = len(luna._cache.cache.get("entries", {}))

    return StatusResponse(
        ready=not luna.processing,
        voice_in=luna.voice_input_enabled,
        voice_out=luna.voice_output_enabled,
        llm_ready=luna._llm.is_ready(),
        cache_entries=cache_entries,
        memory_facts=len(luna._memory.facts),
        memory_history=len(luna._memory.history) // 2,
        writing_model=luna.get_model_mode(),
        processing=luna.processing,
        current_action=getattr(luna, "current_action", None) or "",
    )


@app.post("/api/model")
async def set_writing_model(req: ModelRequest, _key: str = Depends(verify_api_key)):
    """Muda o modelo M (Medium 3B) ou H (High 7B) de Escrita e responde o status."""
    if req.mode not in ("medium", "high"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'medium' ou 'high'.")
    luna = get_luna()
    msg = luna.select_model(req.mode)
    return {"success": True, "message": msg, "mode": req.mode}


@app.get("/api/apps")
async def list_apps(_key: str = Depends(verify_api_key)):
    """Lista aplicativos disponíveis no sistema."""
    luna = get_luna()
    names = luna._executor.get_app_names()
    return {"apps": names, "total": len(names)}


@app.get("/api/memory/stats")
async def memory_stats(_key: str = Depends(verify_api_key)):
    """Estatísticas de memória."""
    luna = get_luna()
    return {
        "history_exchanges": len(luna._memory.history) // 2,
        "persistent_facts": len(luna._memory.facts),
        "stats_text": luna._memory.stats(),
    }


@app.get("/api/memory/facts")
async def get_facts(
    query: Optional[str] = None,
    limit: int = 10,
    _key: str = Depends(verify_api_key),
):
    """Consulta fatos da memória persistente."""
    luna = get_luna()
    if query:
        facts = luna._memory.recall(query, limit=limit)
        return {"query": query, "facts": facts}
    return {"facts": [f["fact"] for f in luna._memory.facts[:limit]]}


@app.post("/api/memory/facts")
async def add_fact(req: FactRequest, _key: str = Depends(verify_api_key)):
    """Adiciona um fato à memória persistente."""
    luna = get_luna()
    luna._memory.remember(req.fact, category=req.category, importance=req.importance)
    return {"success": True, "message": f"Fato adicionado: '{req.fact[:50]}...'"}


@app.post("/api/memory/clear")
async def clear_history(_key: str = Depends(verify_api_key)):
    """Limpa histórico da sessão (não apaga fatos persistentes)."""
    luna = get_luna()
    luna._memory.clear_history()
    return {"success": True, "message": "Histórico da sessão limpo."}


@app.get("/api/cache/stats")
async def cache_stats(_key: str = Depends(verify_api_key)):
    """Estatísticas do cache inteligente."""
    luna = get_luna()
    if hasattr(luna, '_cache') and luna._cache:
        stats = luna._cache.get_stats()
        return stats
    return {"message": "Cache não ativo."}


@app.post("/api/cache/clear")
async def clear_cache(_key: str = Depends(verify_api_key)):
    """Limpa cache expirado."""
    luna = get_luna()
    if hasattr(luna, '_cache') and luna._cache:
        removed = luna._cache.clear_all()
        return {"success": True, "removed": removed, "message": f"{removed} entradas removidas do cache."}
    return {"message": "Cache não ativo."}


@app.get("/api/performance")
async def performance_report(_key: str = Depends(verify_api_key)):
    """Relatório de performance do sistema."""
    luna = get_luna()
    if hasattr(luna, '_perf') and luna._perf:
        return {
            "avg_request_ms": luna._perf.get_average_time("request_times"),
            "avg_model_ms": luna._perf.get_average_time("model_times"),
            "cache_hits": luna._perf.metrics.get("cache_hits", 0),
            "cache_misses": luna._perf.metrics.get("cache_misses", 0),
        }
    return {"message": "Monitor de performance não ativo."}


# ── Endpoints de sessões SQL ──────────────────────────────────

@app.get("/api/sessions")
async def list_sessions_endpoint(_key: str = Depends(verify_api_key)):
    """Lista todas as sessões de chat."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    return {"sessions": db.list_sessions()}


@app.post("/api/sessions")
async def create_session_endpoint(req: SessionRequest, _key: str = Depends(verify_api_key)):
    """Cria uma nova sessão de chat."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    db.create_session(req.session_id, req.title)
    # Troca sessão ativa na memória
    luna = get_luna()
    luna._memory.switch_session(req.session_id)
    luna._reset_sticky_state()
    return {"success": True, "session_id": req.session_id}


@app.patch("/api/sessions")
async def rename_session_endpoint(req: RenameSessionRequest, _key: str = Depends(verify_api_key)):
    """Renomeia uma sessão."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    ok = db.rename_session(req.session_id, req.new_title)
    return {"success": ok}


@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, _key: str = Depends(verify_api_key)):
    """Deleta uma sessão e seu histórico."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    ok = db.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Sessão não encontrada ou protegida.")
    return {"success": True}


@app.get("/api/sessions/{session_id}/history")
async def session_history_endpoint(
    session_id: str,
    last_n: int = 50,
    _key: str = Depends(verify_api_key),
):
    """Retorna histórico de mensagens de uma sessão."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    return {"session_id": session_id, "messages": db.get_history(session_id, last_n)}


@app.post("/api/sessions/switch")
async def switch_session_endpoint(req: SessionRequest, _key: str = Depends(verify_api_key)):
    """Troca a sessão ativa."""
    from brain.chat_db import get_chat_db
    db = get_chat_db()
    db.create_session(req.session_id)  # garante que existe
    luna = get_luna()
    luna._memory.switch_session(req.session_id)
    luna._reset_sticky_state()
    return {"success": True, "active_session": req.session_id}


# ── Controle de Voz ───────────────────────────────────────────

@app.post("/api/voice/input/toggle")
async def toggle_voice_input(_key: str = Depends(verify_api_key)):
    """Liga/desliga entrada de voz (wakeword + STT)."""
    luna = get_luna()
    enabled = luna.toggle_voice_input()
    return {"enabled": enabled}


@app.post("/api/voice/output/toggle")
async def toggle_voice_output(_key: str = Depends(verify_api_key)):
    """Liga/desliga saída de voz (TTS)."""
    luna = get_luna()
    enabled = luna.toggle_voice_output()
    return {"enabled": enabled}


@app.post("/api/voice/listen")
async def listen_once(_key: str = Depends(verify_api_key)):
    """Escuta uma frase e retorna o texto transcrito."""
    luna = get_luna()
    if not luna.voice_input_enabled:
        raise HTTPException(status_code=400, detail="Entrada de voz desativada.")
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, luna.listen)
    return {"text": text or ""}


@app.post("/api/voice/speak")
async def speak_text(req: ChatRequest, _key: str = Depends(verify_api_key)):
    """Faz a Luna falar um texto."""
    luna = get_luna()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, luna.speak, req.message)
    return {"success": True}


# ── Controles de Mídia ────────────────────────────────────────


@app.post("/api/media")
async def media_control(req: MediaRequest, _key: str = Depends(verify_api_key)):
    """Controla reprodução de mídia via playerctl."""
    from actions.media import get_media
    media = get_media()
    actions = {
        "play":        media.play,
        "pause":       media.pause,
        "play_pause":  media.play_pause,
        "next":        media.next_track,
        "prev":        media.prev_track,
        "stop":        media.stop,
        "mute":        media.mute,
        "volume_up":   lambda: media.volume_up(req.value),
        "volume_down": lambda: media.volume_down(req.value),
        "now_playing": media.now_playing,
    }
    fn = actions.get(req.action)
    if not fn:
        raise HTTPException(status_code=400, detail=f"Ação desconhecida: {req.action}")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, fn)
    return {"result": result}


# ── Timer ─────────────────────────────────────────────────────


@app.post("/api/timer")
async def add_timer(req: TimerRequest, _key: str = Depends(verify_api_key)):
    get_luna()._executor.timer.add_timer(req.seconds, req.name)
    return {"success": True, "name": req.name, "seconds": req.seconds}

@app.get("/api/timer")
async def timer_status(_key: str = Depends(verify_api_key)):
    import time as _time
    t = get_luna()._executor.timer
    now = _time.time()
    active = [{"name": n, "remaining_s": max(0, int(e - now))}
              for n, e in t.timer_ends.items() if e - now > 0]
    return {"timers": active, "status": t.status()}

@app.get("/api/shopping")
async def get_shopping(_key: str = Depends(verify_api_key)):
    s = get_luna()._executor.shopping
    data = s._load()  # sempre lê do disco (fonte de verdade)
    return {"items": data.get("items", [])}

@app.post("/api/shopping")
async def add_shopping(req: NoteRequest, _key: str = Depends(verify_api_key)):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Item vazio.")
    result = get_luna()._executor.shopping.handle(f"adiciona {req.text.strip()}")
    return {"success": True, "result": result}

@app.delete("/api/shopping/{item}")
async def remove_shopping(item: str, _key: str = Depends(verify_api_key)):
    result = get_luna()._executor.shopping.handle(f"já comprei {item}")
    return {"success": True, "result": result}

@app.delete("/api/timer/{name}")
async def cancel_timer(name: str, _key: str = Depends(verify_api_key)):
    from actions.timer import get_timer
    ok = get_timer().cancel_timer(name)
    return {"success": ok}


# ── Notas ─────────────────────────────────────────────────────


@app.get("/api/notes")
async def list_notes(_key: str = Depends(verify_api_key)):
    notes = get_luna()._executor.notes
    return {"notes": [{"index": i+1, "text": n["text"], "ts": n.get("ts","")} for i, n in enumerate(notes._notes)]}

@app.post("/api/notes")
async def add_note(req: NoteRequest, _key: str = Depends(verify_api_key)):
    result = get_luna()._executor.notes.add(req.text)
    return {"success": True, "result": result}

@app.delete("/api/notes/{index}")
async def delete_note(index: int, _key: str = Depends(verify_api_key)):
    result = get_luna()._executor.notes.delete(index)
    return {"success": True, "result": result}


# ── Lembretes ─────────────────────────────────────────────────


@app.get("/api/reminders")
async def list_reminders(_key: str = Depends(verify_api_key)):
    return {"reminders": get_luna()._executor.reminders.list_reminders()}

@app.post("/api/reminders")
async def add_reminder(req: ReminderRequest, _key: str = Depends(verify_api_key)):
    r = get_luna()._executor.reminders
    # Campos estruturados (formulário web)
    if req.hour >= 0 and req.message:
        from datetime import datetime as _dt, timedelta as _td
        now = _dt.now()
        # Parse date
        if req.date:
            try:
                parts = req.date.split("/")
                day, month = int(parts[0]), int(parts[1])
                year = int(parts[2]) if len(parts) > 2 else now.year
                when = _dt(year, month, day, req.hour, req.minute)
            except Exception:
                when = now.replace(hour=req.hour, minute=req.minute, second=0, microsecond=0)
                if when <= now:
                    when += _td(days=1)
        else:
            when = now.replace(hour=req.hour, minute=req.minute, second=0, microsecond=0)
            if when <= now:
                when += _td(days=1)
        result = r.add(req.message, when)
    else:
        # Linguagem natural
        text = req.text or req.message
        if not text:
            return {"success": False, "result": "Texto vazio."}
        # Garante que tem trigger word
        if not any(w in text.lower() for w in ["me lembra", "me lembre", "lembra", "lembrete"]):
            text = "me lembra de " + text
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, r.handle, text)
    return {"success": True, "result": result or "Lembrete adicionado."}


# ── Clima ─────────────────────────────────────────────────────

@app.get("/api/weather")
async def get_weather(city: str = "", _key: str = Depends(verify_api_key)):
    from actions.weather import get_weather as _gw
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _gw().get_weather, city)
    return {"result": result}


@app.get("/api/briefing")
async def daily_briefing(_key: str = Depends(verify_api_key)):
    """Briefing diário: clima SP + Itapecerica, lembretes, notas, frase do dia."""
    luna = get_luna()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, luna._daily_briefing)
    return {"result": result}


# ── Stop ─────────────────────────────────────────────────────

@app.post("/api/stop")
async def stop_processing(_key: str = Depends(verify_api_key)):
    """Para LLM, TTS e processamento imediatamente."""
    get_luna().stop()
    return {"stopped": True}


# ── Chat streaming (SSE) ──────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(request: Request, req: ChatRequest, _key: str = Depends(verify_api_key)):
    """
    Streaming SSE da resposta da Luna.
    Eventos: data: <chunk>\\n\\n  |  data: [DONE]\\n\\n  |  data: [ERROR]...
    """
    _check_rate_limit(request)
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")

    luna = get_luna()

    async def event_gen():
        loop = asyncio.get_event_loop()
        import queue as _queue
        q = _queue.Queue(maxsize=100)

        def progress_cb(event: dict):
            try:
                q.put(("progress", event), block=False)
            except _queue.Full:
                pass

        def run():
            try:
                result = luna.process(message, progress_callback=progress_cb)
                q.put(("done", result))
            except Exception as e:
                try:
                    q.put(("error", str(e)), block=False)
                except _queue.Full:
                    pass

        import threading
        t = threading.Thread(target=run, daemon=True)
        t.start()

        import json as _json
        while True:
            await asyncio.sleep(0.05)
            try:
                kind, data = q.get_nowait()
                if kind == "progress":
                    yield f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"
                    continue
                if kind == "done":
                    yield f"data: {_json.dumps({'type': 'done', 'text': data}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {_json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                break
            except _queue.Empty:
                if not t.is_alive():
                    break
                continue

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── TTS stream — gera áudio e serve como arquivo ──────────────

@app.post("/api/tts/stream")
async def tts_stream(req: ChatRequest, _key: str = Depends(verify_api_key)):
    """Gera áudio TTS do texto e retorna como audio/mpeg."""
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texto vazio.")

    import tempfile, os as _os
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        # Gera via edge-tts diretamente
        import edge_tts
        from config import VOICE_CONFIG
        communicate = edge_tts.Communicate(
            text,
            VOICE_CONFIG.get("voice", "pt-BR-ThalitaMultilingualNeural"),
            rate=VOICE_CONFIG.get("rate", "+5%"),
            pitch=VOICE_CONFIG.get("pitch", "+2Hz"),
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: asyncio.run(communicate.save(tmp_path)))

        def iterfile():
            with open(tmp_path, "rb") as f:
                yield from f
            _os.unlink(tmp_path)

        return StreamingResponse(iterfile(), media_type="audio/mpeg",
                                 headers={"Content-Disposition": "inline"})
    except Exception as e:
        if _os.path.exists(tmp_path):
            _os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"TTS falhou: {e}")


# ── STT — recebe áudio WebM e transcreve ─────────────────────

@app.post("/api/stt")
async def stt_transcribe(request: Request, _key: str = Depends(verify_api_key)):
    """Recebe áudio (webm/ogg/wav) e retorna transcrição via Whisper local."""
    _check_rate_limit(request)
    import tempfile, os as _os, subprocess as _sp
    MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25MB
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo 25MB.")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Áudio vazio.")
    if len(body) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo 25MB.")
    if body[:4] not in (b"RIFF", b"OggS", b"fLaC", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        pass  # Allow anyway, just a warning

    content_type = request.headers.get("content-type", "audio/webm")
    ext = ".webm" if "webm" in content_type else ".ogg" if "ogg" in content_type else ".wav"

    tmp_in = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp_in.write(body)
    tmp_in.close()
    tmp_wav = tmp_in.name.replace(ext, ".wav")

    try:
        _sp.run(
            ["ffmpeg", "-y", "-i", tmp_in.name, "-ar", "16000", "-ac", "1", tmp_wav],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True
        )
        from faster_whisper import WhisperModel
        global _whisper_model
        if _whisper_model is None:
            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        model = _whisper_model
        segments, _ = model.transcribe(tmp_wav, language="pt", beam_size=1, vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        return {"text": text}
    except Exception as e:
        return {"text": "", "error": str(e)}
    finally:
        for f in [tmp_in.name, tmp_wav]:
            try: _os.unlink(f)
            except: pass


# ── Sistema ───────────────────────────────────────────────────

@app.get("/api/system/metrics")
async def system_metrics(_key: str = Depends(verify_api_key)):
    """CPU, RAM, disco."""
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_gb": round(psutil.virtual_memory().used / 1e9, 1),
            "ram_total_gb": round(psutil.virtual_memory().total / 1e9, 1),
            "disk_percent": psutil.disk_usage("/").percent,
        }
    except ImportError:
        return {"error": "psutil não instalado"}

@app.get("/api/system/facts")
async def system_facts(_key: str = Depends(verify_api_key)):
    """Fatos persistentes da memória."""
    luna = get_luna()
    return {"facts": luna._memory.facts}

@app.delete("/api/system/facts")
async def clear_facts(_key: str = Depends(verify_api_key)):
    luna = get_luna()
    luna._memory.facts = []
    luna._memory._force_save()
    return {"success": True}

@app.get("/api/system/apps")
async def system_apps(_key: str = Depends(verify_api_key)):
    luna = get_luna()
    return {"apps": luna._executor.get_app_names()}

@app.post("/api/system/apps/open")
async def open_app(req: NoteRequest, _key: str = Depends(verify_api_key)):
    luna = get_luna()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, luna._executor.open_app, req.text)
    return result


# ── Servir arquivos estáticos de web/ ─────────────────────────

_web_dir = Path(__file__).parent / "web"
# ── Joy Mode — Jogos com IA ───────────────────────────────────

class JoyStartRequest(BaseModel):
    game: str
    difficulty: str = "medio"
    session_id: str = "default"

class JoyActionRequest(BaseModel):
    action: str
    session_id: str = "default"
    data: dict = {}

class JoyChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    game: str = ""

@app.get("/api/joy/games")
async def joy_list_games(_key: str = Depends(verify_api_key)):
    from actions.joy_games import list_games
    return {"games": list_games()}

@app.post("/api/joy/start")
async def joy_start(req: JoyStartRequest, _key: str = Depends(verify_api_key)):
    from actions.joy_games import create_joy_session
    return create_joy_session(req.session_id, req.game, req.difficulty)

@app.post("/api/joy/action")
async def joy_action_endpoint(req: JoyActionRequest, _key: str = Depends(verify_api_key)):
    from actions.joy_games import joy_action
    return joy_action(req.session_id, req.action, req.data)

@app.post("/api/joy/chat")
async def joy_chat(req: JoyChatRequest, _key: str = Depends(verify_api_key)):
    """Luna conversa durante o jogo — não revela estratégia."""
    luna = get_luna()
    game_ctx = f" Estamos jogando {req.game}." if req.game else ""
    prompt = (
        f"Você é Luna, uma IA jogando um jogo com o usuário.{game_ctx} "
        f"Responda de forma divertida, animada e curta (máx 2 frases). "
        f"NUNCA revele suas próximas jogadas ou estratégia. "
        f"Mensagem do usuário: {req.message}"
    )
    loop = asyncio.get_event_loop()
    from brain.llm import MODELS
    llm = luna._llm
    response = await loop.run_in_executor(
        None,
        lambda: llm.generate(prompt, task_type="command", model=MODELS["fast"])
    )
    # Remove JSON wrapper se vier
    import re as _re
    clean = _re.sub(r'^\{.*?"response"\s*:\s*"', '', str(response), flags=_re.DOTALL)
    clean = _re.sub(r'"\s*,?\s*"action".*$', '', clean, flags=_re.DOTALL).strip().strip('"')
    if not clean or clean.startswith("{"):
        clean = str(response)
    return {"response": clean}

@app.get("/joy", include_in_schema=False)
async def joy_page():
    joy_path = Path(__file__).parent / "web" / "joy.html"
    if joy_path.exists():
        return FileResponse(joy_path)
    raise HTTPException(status_code=404, detail="joy.html não encontrado.")


# ── Luna Write Mode ──────────────────────────────────────────

class WriteStreamRequest(BaseModel):
    prompt: str
    project_id: str = ""
    context_text: str = ""
    style: str = "neutro"
    characters: str = ""
    chapter: int = 0

class WriteProjectRequest(BaseModel):
    title: str
    genre: str = "ficção"
    style: str = "neutro"
    characters: list = []

class WriteTextUpdate(BaseModel):
    text: str

class WriteChapterRequest(BaseModel):
    title: str = ""

class WriteCharacterRequest(BaseModel):
    name: str
    age: int = 0
    voice: str = ""
    traits: str = ""
    context: str = ""


@app.get("/write", include_in_schema=False)
async def write_page():
    write_path = Path(__file__).parent / "web" / "write.html"
    if write_path.exists():
        return FileResponse(write_path)
    raise HTTPException(status_code=404, detail="write.html não encontrado.")


@app.get("/api/write/projects")
async def list_write_projects(_key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    return {"projects": wm.list_projects()}


@app.post("/api/write/projects")
async def create_write_project(req: WriteProjectRequest, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    proj = wm.create_project(
        title=req.title,
        genre=req.genre,
        style=req.style,
        characters=req.characters,
    )
    return {"success": True, "project": proj.to_dict()}


@app.get("/api/write/project/{project_id}")
async def get_write_project(project_id: str, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    proj = wm.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return proj.to_dict()


@app.put("/api/write/project/{project_id}")
async def update_write_text(project_id: str, req: WriteTextUpdate, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    ok = wm.update_text(project_id, req.text)
    if not ok:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"success": True}


@app.post("/api/write/project/{project_id}/chapter")
async def add_write_chapter(project_id: str, req: WriteChapterRequest, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    result = wm.add_chapter(project_id, req.title)
    if not result:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return result


@app.post("/api/write/project/{project_id}/character")
async def add_write_character(project_id: str, req: WriteCharacterRequest, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    ok = wm.add_character(project_id, {
        "name": req.name, "age": req.age, "voice": req.voice,
        "traits": req.traits, "context": req.context,
    })
    if not ok:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"success": True}


@app.delete("/api/write/project/{project_id}")
async def delete_write_project(project_id: str, _key: str = Depends(verify_api_key)):
    from actions.write_mode import get_write_mode
    wm = get_write_mode()
    ok = wm.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"success": True}


@app.post("/api/write/stream")
async def write_stream(req: WriteStreamRequest, _key: str = Depends(verify_api_key)):
    """Streaming SSE — gera texto criativo em tempo real."""
    from actions.writer import get_writer
    from actions.write_mode import get_write_mode
    from brain.llm import get_llm, GROQ_MODELS, MODELS

    writer = get_writer()
    wm = get_write_mode()
    llm = get_llm()
    luna = get_luna()

    proj = wm.get_project(req.project_id) if req.project_id else None
    style = req.style or (proj.style if proj else "neutro")
    characters = req.characters or (proj.get_characters_prompt() if proj else "")
    context_text = req.context_text or (proj.get_context_summary() if proj else "")

    async def event_gen():
        import queue as _queue, threading, json as _json

        q = _queue.Queue()

        def run():
            try:
                # Fase 1: Planning
                plan_prompt = writer.build_planning_prompt(req.prompt)
                fast_model = GROQ_MODELS.get("fast", MODELS.get("fast", ""))
                plan_text = llm.generate(plan_prompt, task_type="planning", model=fast_model)
                q.put(("phase", "planning_done"))

                # Fase 2: Streaming Draft
                if req.chapter > 0:
                    draft_prompt = writer.build_chapter_prompt(
                        plan_text, req.prompt, context_text, req.chapter, characters
                    )
                else:
                    draft_prompt = writer.build_draft_prompt(
                        plan_text, req.prompt, context_text, characters, style
                    )

                model_key = luna._writing_model if hasattr(luna, '_writing_model') else "main"
                model_name = MODELS.get(model_key, MODELS["main"])

                stream_gen = llm.generate(
                    draft_prompt, task_type="creative",
                    model=model_name, stream=True,
                )

                first_line_done = False
                buffer = ""
                for chunk in stream_gen:
                    if not first_line_done:
                        buffer += str(chunk)
                        if "\n" in buffer:
                            _, rest = buffer.split("\n", 1)
                            if rest:
                                clean = writer.clean_chunk(rest)
                                q.put(("text", clean))
                            first_line_done = True
                    else:
                        clean = writer.clean_chunk(str(chunk))
                        q.put(("text", clean))

                q.put(("done", ""))
            except Exception as e:
                q.put(("error", str(e)))

        threading.Thread(target=run, daemon=True).start()

        while True:
            await asyncio.sleep(0.03)
            try:
                kind, data = q.get_nowait()
                import json as _json
                yield f"data: {_json.dumps({'type': kind, 'content': data})}\n\n"
                if kind in ("done", "error"):
                    break
            except _queue.Empty:
                continue

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if _web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_web_dir)), name="static")

@app.post("/api/image/generate")
async def api_generate_image(req: Request, _key: str = Depends(verify_api_key)):
    """Gera imagem via Google Gemini (Imagen). Gratuito com a API key do Gemini."""
    try:
        body = await req.json()
        prompt = body.get("prompt", "")
        size = body.get("size", "1024x1024")
        if not prompt:
            return {"success": False, "error": "Prompt não fornecido."}
        from actions.image_gen import generate_image
        result = generate_image(prompt, size)
        if result.startswith("SUCESSO:"):
            path = result.replace("SUCESSO: Imagem gerada e salva em ", "").strip()
            return {"success": True, "path": path, "message": f"Imagem salva em {path}"}
        return {"success": False, "error": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/shutdown")
async def shutdown(request: Request, _key: str = Depends(verify_api_key)):
    admin_user = _require_admin(request)
    _log_admin_action(admin_user, "shutdown", "Desligou o backend")
    import os, signal, asyncio
    print("🛑 Shutting down Luna Backend...")
    async def exit_later():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)
    asyncio.create_task(exit_later())
    return {"success": True, "message": "Backend shutting down..."}


# ── Função para iniciar o servidor ────────────────────────────

def run_server(host: str = None, port: int = None):
    """Inicia o servidor FastAPI com uvicorn."""
    import uvicorn
    import os
    from pathlib import Path as _Path
    _host = host or config.API_HOST
    _port = port or config.API_PORT

    _ssl_key  = _Path(__file__).parent / "config" / "ssl" / "key.pem"
    _ssl_cert = _Path(__file__).parent / "config" / "ssl" / "cert.pem"
    _https = os.getenv("LUNA_USE_HTTPS", "false").lower() == "true" and _ssl_key.exists() and _ssl_cert.exists()
    _scheme = "https" if _https else "http"

    logger.info(f"Luna API (FastAPI + Uvicorn)")
    logger.info(f"Local: {_scheme}://localhost:{_port}")
    logger.info(f"Rede:  {_scheme}://0.0.0.0:{_port}")
    logger.info(f"Docs:  {_scheme}://localhost:{_port}/docs")
    if _https:
        logger.info(f"HTTPS ativo (certificado self-signed)")
    logger.info(f"API Key: {'*' * 8}{config.API_KEY[-4:]}")

    _kwargs = dict(host=_host, port=_port, log_level="warning", access_log=False)
    if _https:
        _kwargs["ssl_keyfile"]  = str(_ssl_key)
        _kwargs["ssl_certfile"] = str(_ssl_cert)

    uvicorn.run(app, **_kwargs)


def start_server_thread(host: str = None, port: int = None):
    """Inicia o servidor em uma thread daemon (para uso com app.py/Qt)."""
    import threading
    t = threading.Thread(
        target=run_server,
        args=(host, port),
        daemon=True,
    )
    t.start()
    return t


if __name__ == "__main__":
    run_server()
