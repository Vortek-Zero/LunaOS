#!/usr/bin/env python3
"""
brain/llm.py — LLM híbrido + Crew Mode: Mistral → Gemini → OpenRouter → ... → Puter

Prioridade:
  1. Mistral           → mistral-large/small (primário quando key disponível)
  2. Gemini 2.5 Flash  → direto via SDK (grátis, ~1500 req/dia)
  3. OpenRouter        → DeepSeek-V3 via OpenRouter (se tiver créditos)
  4. Completions.me    → Claude Opus 4.6, GPT-5.2, Gemini 3.1 Pro (grátis, ilimitado)
  5. Chutes.ai         → DeepSeek-V3.2-TEE (se tiver créditos)
  6. GitHub Models     → DeepSeek-V3-0324 / DeepSeek-R1 (free tier — rate limitado)
  7. Naga AI           → Nemotron 3, Llama (gratuito)
  8. Best AI           → DeepSeek, Qwen, Gemini (gratuito)
  9. Groq              → qwen3-32b, llama-4-scout (free tier)
  10. FreeTheAi         → GPT-5.5, GLM, Nemotron (grátis, Discord check-in)
  11. Puter             → gpt-5.2, gpt-5, o3, grok-3, claude-sonnet-5, deepseek-r1-0528 (dev tier)
"""

import json
import os
import re
import time
import time as _time
from collections.abc import Generator
from dataclasses import dataclass

from error_codes import err as luna_err

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from mistralai.client import Mistral

    HAS_MISTRAL = True
except ImportError:
    HAS_MISTRAL = False

try:
    import google.generativeai as genai

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from groq import Groq as GroqClient

    HAS_GROQ_LIB = True
except ImportError:
    HAS_GROQ_LIB = False

try:
    from config import (
        BESTAI_API_KEY,
        BESTAI_BASE_URL,
        BESTAI_MODELS,
        CASCADE_ORDER,
        CHUTES_API_KEY,
        CHUTES_BASE_URL,
        CHUTES_MODELS,
        COMPLETIONS_API_KEY,
        COMPLETIONS_BASE_URL,
        COMPLETIONS_MODELS,
        CREW_ENABLED,
        CREW_MODELS,
        FREETHEAI_API_KEY,
        FREETHEAI_BASE_URL,
        FREETHEAI_MODELS,
        GEMINI_API_KEY,
        GEMINI_MODELS,
        GITHUB_BASE_URL,
        GITHUB_MODELS,
        GITHUB_TOKEN,
        GROQ_API_KEY,
        GROQ_MODELS,
        MISTRAL_API_KEY,
        MISTRAL_MODELS,
        MODEL_TIMEOUTS,
        MODELS,
        NAGA_API_KEY,
        NAGA_BASE_URL,
        NAGA_MODELS,
        OPENROUTER_API_KEY,
        OPENROUTER_BASE_URL,
        OPENROUTER_MODELS,
        PUTER_API_BASE_URL,
        PUTER_LLM_MODELS,
        PUTER_TOKEN,
    )
except ImportError:
    MODELS = {
        "heavy": "qwen2.5:7b-instruct-q4_K_M",
        "main": "qwen2.5:3b",
        "fast": "qwen2.5:0.5b-instruct-fp16",
        "basic": "qwen2.5:0.5b",
    }
    MODEL_TIMEOUTS = {"fast": 30, "main": 120, "heavy": 600}
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODELS = {
        "heavy": "mistral-large-latest",
        "main": "mistral-large-latest",
        "fast": "mistral-small-latest",
    }
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODELS = {
        "heavy": "llama-3.3-70b-versatile",
        "main": "llama-3.1-8b-instant",
        "fast": "llama-3.1-8b-instant",
    }
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELS = {
        "heavy": "gemini-2.5-flash",
        "main": "gemini-2.5-flash",
        "fast": "gemini-2.5-flash",
    }
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_BASE_URL = "https://models.inference.ai.azure.com"
    GITHUB_MODELS = {
        "heavy": "DeepSeek-R1",
        "main": "DeepSeek-V3-0324",
        "fast": "DeepSeek-V3-0324",
        "fallback": "DeepSeek-R1",
    }
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_MODELS = {
        "heavy": "deepseek/deepseek-chat-v3-0324",
        "main": "deepseek/deepseek-chat-v3-0324",
        "fast": "deepseek/deepseek-chat-v3-0324",
        "fallback": "deepseek/deepseek-r1",
        "fallback2": "google/gemini-2.5-flash",
    }
    CHUTES_API_KEY = os.getenv("CHUTES_API_KEY", "")
    CHUTES_BASE_URL = os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
    CHUTES_MODELS = {
        "heavy": "deepseek-ai/DeepSeek-V3.2-TEE",
        "main": "deepseek-ai/DeepSeek-V3.2-TEE",
        "fast": "Qwen/Qwen3.6-27B-TEE",
        "fallback": "google/gemma-4-31B-turbo-TEE",
        "fallback2": "MiniMaxAI/MiniMax-M2.5-TEE",
    }
    NAGA_API_KEY = os.getenv("NAGA_API_KEY", "")
    NAGA_BASE_URL = "https://api.naga.ac/v1"
    NAGA_MODELS = {
        "heavy": "nemotron-3-ultra-550b-a55b:free",
        "main": "nemotron-3-super-120b-a12b:free",
        "fast": "llama-4-scout-17b-16e-instruct:free",
        "fallback": "llama-3.3-70b-instruct:free",
    }
    BESTAI_API_KEY = os.getenv("BESTAI_API_KEY", "")
    BESTAI_BASE_URL = "https://api.oaibest.com/v1"
    BESTAI_MODELS = {
        "heavy": "deepseek-r1",
        "main": "deepseek-v3.1",
        "fast": "deepseek-v4-flash",
        "fallback": "qwen3.5-flash",
    }
    FREETHEAI_API_KEY = os.getenv("FREETHEAI_API_KEY", "")
    FREETHEAI_BASE_URL = "https://api.freetheai.xyz/v1"
    FREETHEAI_MODELS = {
        "heavy": "bbl/gpt-5.5-mini",
        "main": "glm/glm-5.1",
        "fast": "opc/deepseek-v4-flash-free",
        "fallback": "opc/nemotron-3-ultra-free",
    }
    PUTER_TOKEN = os.getenv("PUTER_TOKEN", "")
    PUTER_API_BASE_URL = "https://api.puter.com"
    PUTER_LLM_MODELS = {
        "heavy": "gpt-5",
        "main": "o3",
        "fast": "gpt-4o-mini",
    }
    CASCADE_ORDER = [
        "mistral",
        "gemini",
        "openrouter",
        "completions",
        "chutes",
        "github",
        "naga",
        "bestai",
        "groq",
        "freetheai",
        "puter",
    ]
    CREW_ENABLED = True
    CREW_MODELS = {
        "conversational": "puter/grok-3",
        "creative": "puter/grok-3",
        "default": "puter/grok-3",
        "coding": "puter/gpt-5.2",
        "planning": "puter/o3",
        "factual": "puter/deepseek-r1-0528",
        "command": "puter/gpt-4o-mini",
        "writing": "puter/claude-sonnet-5",
        "compat": "puter/gpt-4o",
    }


@dataclass
class ToolCallFunction:
    name: str
    arguments: str


@dataclass
class NormalizedToolCall:
    id: str
    type: str
    function: ToolCallFunction


def _normalize_tool_calls(raw_tool_calls) -> list:
    if not raw_tool_calls:
        return []
    result = []
    for tc in raw_tool_calls:
        try:
            if isinstance(tc, dict):
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                result.append(
                    NormalizedToolCall(
                        id=tc.get("id", f"call_{len(result)}"),
                        type=tc.get("type", "function"),
                        function=ToolCallFunction(
                            name=fn.get("name", ""),
                            arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                        ),
                    )
                )
            else:
                fn = tc.function
                result.append(
                    NormalizedToolCall(
                        id=getattr(tc, "id", f"call_{len(result)}"),
                        type=getattr(tc, "type", "function"),
                        function=ToolCallFunction(name=fn.name, arguments=fn.arguments),
                    )
                )
        except Exception as e:
            print(f"[LLM] ⚠ Erro ao normalizar tool_call: {e}")
    return result


def _parse_sse_stream(response) -> Generator[str]:
    """Shared SSE stream parser for OpenAI-compatible chat completions APIs."""
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line.startswith("data: "):
            line = line[6:]
        if line == "[DONE]":
            break
        try:
            chunk = json.loads(line)
            delta = chunk["choices"][0].get("delta", {}).get("content")
            if delta:
                yield delta
        except Exception:
            continue


TASK_PARAMS = {
    "factual": {"temperature": 0.05, "top_p": 0.85, "max_tokens": 500},
    "creative": {"temperature": 0.85, "top_p": 0.95, "max_tokens": 3000},
    "command": {"temperature": 0.1, "top_p": 0.90, "max_tokens": 200},
    "planning": {"temperature": 0.15, "top_p": 0.90, "max_tokens": 500},
    "coding": {"temperature": 0.1, "top_p": 0.90, "max_tokens": 4000},
    "conversational": {"temperature": 0.70, "top_p": 0.95, "max_tokens": 1500},
    "default": {"temperature": 0.2, "top_p": 0.90, "max_tokens": 500},
}


class LLMWrapper:
    """
    Interface unificada: Gemini 2.5 Flash → Groq → Ollama.
    Fallback automático e transparente para o resto do sistema.
    """

    def __init__(self, model: str = None):
        self.model = model or MODELS["main"]
        self.available = False
        self._stop_flag = False
        self._crew_enabled = CREW_ENABLED

        # ── Mistral (primário) ────────────────────────────────────────
        self._mistral_ok = HAS_MISTRAL and bool(MISTRAL_API_KEY)
        self._mistral_rl_until = 0.0
        self._mistral_client = None
        if self._mistral_ok:
            try:
                self._mistral_client = Mistral(api_key=MISTRAL_API_KEY)
                print(f"[LLM] ✓ Mistral ativo — {MISTRAL_MODELS['main']}")
                self.available = True
            except Exception as e:
                print(luna_err("MISTRAL_API_ERROR", f"Inicialização: {e}"))
                self._mistral_ok = False

        # ── Gemini (fallback 1) ───────────────────────────────────────
        self._gemini_ok = HAS_GEMINI and bool(GEMINI_API_KEY)
        self._gemini_rl_until = 0.0
        self._gemini_rl_per_model: dict = {}  # {model_name: timestamp} rate limit por modelo
        self._gemini_client = None
        if self._gemini_ok:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                # Testa com uma chamada mínima
                self._gemini_client = genai.GenerativeModel(GEMINI_MODELS["fast"])
                fb = GEMINI_MODELS.get("fallback", "gemini-2.0-flash")
                fb2 = GEMINI_MODELS.get("fallback2", "gemini-2.5-flash-lite")
                print(f"[LLM] ✓ Gemini ativo — {GEMINI_MODELS['main']} → {fb} → {fb2}")
                self.available = True
            except Exception as e:
                print(luna_err("GEMINI_INIT_FAILED", str(e)))
                self._gemini_ok = False

        # ── OpenRouter (DeepSeek V3 via OpenRouter — se tiver créditos) ──
        self._openrouter_ok = HAS_REQUESTS and bool(OPENROUTER_API_KEY)
        self._openrouter_rl_per_model: dict = {}
        if self._openrouter_ok:
            print(f"[LLM] ✓ OpenRouter ativo — {OPENROUTER_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Completions.me (gratuito, ilimitado — Claude, GPT, Gemini, Grok) ──
        self._completions_ok = HAS_REQUESTS and bool(COMPLETIONS_API_KEY)
        self._completions_rl_until = 0.0
        if self._completions_ok:
            print(f"[LLM] ✓ Completions.me ativo — {COMPLETIONS_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Chutes.ai (DeepSeek-V3.2-TEE — já tem key com créditos) ──
        self._chutes_ok = HAS_REQUESTS and bool(CHUTES_API_KEY)
        self._chutes_rl_until = 0.0
        if self._chutes_ok:
            print(f"[LLM] ✓ Chutes.ai ativo — {CHUTES_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── GitHub Models (fallback 4) ────────────────────────
        self._github_ok = HAS_REQUESTS and bool(GITHUB_TOKEN)
        self._github_rl_per_model: dict = {}
        if self._github_ok:
            print(f"[LLM] ✓ GitHub Models ativo (fallback 1) — {GITHUB_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Naga AI API (fallback 5) ──────────────────────────
        self._naga_ok = HAS_REQUESTS and bool(NAGA_API_KEY)
        self._naga_rl_until = 0.0
        if self._naga_ok:
            print(f"[LLM] ✓ Naga AI ativo (fallback 5) — {NAGA_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Best AI API (fallback 6) ──────────────────────────
        self._bestai_ok = HAS_REQUESTS and bool(BESTAI_API_KEY)
        self._bestai_rl_until = 0.0
        if self._bestai_ok:
            print(f"[LLM] ✓ Best AI ativo (fallback 6) — {BESTAI_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Groq (fallback 7) ─────────────────────────────────
        self._groq_ok = HAS_GROQ_LIB and bool(GROQ_API_KEY)
        self._groq_rl_until = 0.0
        self._groq = None
        if self._groq_ok:
            try:
                self._groq = GroqClient(api_key=GROQ_API_KEY)
                print("[LLM] ✓ Groq API ativo (fallback 7)")
                if not self.available:
                    self.available = True
            except Exception as e:
                print(luna_err("GROQ_INIT_FAILED", str(e)))
                self._groq_ok = False

        # ── FreeTheAi (fallback 10) ──────────────────────────
        self._freetheai_ok = HAS_REQUESTS and bool(FREETHEAI_API_KEY)
        self._freetheai_rl_until = 0.0
        if self._freetheai_ok:
            print(f"[LLM] ✓ FreeTheAi ativo — {FREETHEAI_MODELS['main']}")
            if not self.available:
                self.available = True

        # ── Puter LLM (fallback 11 — gpt-5, o3, gpt-4o via Puter API) ──
        self._puter_ok = HAS_REQUESTS and bool(PUTER_TOKEN)
        self._puter_rl_until = 0.0
        if self._puter_ok:
            print(f"[LLM] ✓ Puter LLM ativo — {PUTER_LLM_MODELS['main']} (dev: {PUTER_LLM_MODELS['heavy']})")
            if not self.available:
                self.available = True

        # ── Cascade registry ────────────────────────────────────
        self._cascade = {
            "mistral": (self._mistral_available, self._mistral_model_for, self._generate_mistral),
            "gemini": (self._gemini_available, self._gemini_model_for, self._generate_gemini),
            "openrouter": (self._openrouter_available, self._openrouter_model_for, self._generate_openrouter),
            "completions": (self._completions_available, self._completions_model_for, self._generate_completions),
            "chutes": (self._chutes_available, self._chutes_model_for, self._generate_chutes),
            "github": (self._github_available, self._github_model_for, self._generate_github),
            "naga": (self._naga_available, self._naga_model_for, self._generate_naga),
            "bestai": (self._bestai_available, self._bestai_model_for, self._generate_bestai),
            "groq": (self._groq_available, self._groq_model_for, self._generate_groq),
            "freetheai": (self._freetheai_available, self._freetheai_model_for, self._generate_freetheai),
            "puter": (self._puter_available, self._puter_model_for, self._generate_puter),
        }

        if HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        else:
            self._session = None

    def _mistral_available(self) -> bool:
        return self._mistral_ok and time.time() >= self._mistral_rl_until

    def _mistral_model_for(self, model_hint: str) -> str:
        mistral_vals = set(MISTRAL_MODELS.values())
        if model_hint in mistral_vals:
            return model_hint
        if model_hint == "heavy" or model_hint == MODELS.get("heavy"):
            return MISTRAL_MODELS["heavy"]
        if model_hint in ("fast", "basic") or model_hint in (MODELS.get("fast"), MODELS.get("basic")):
            return MISTRAL_MODELS["fast"]
        return MISTRAL_MODELS["main"]

    def _gemini_available(self) -> bool:
        if not self._gemini_ok:
            return False
        if time.time() < self._gemini_rl_until:
            return False
        # Verifica se há pelo menos um modelo sem rate limit
        now = time.time()
        models = [GEMINI_MODELS.get(k) for k in ("heavy", "main", "fallback", "fallback2") if GEMINI_MODELS.get(k)]
        return any(now >= self._gemini_rl_per_model.get(m, 0) for m in models)

    def _github_available(self) -> bool:
        if not self._github_ok:
            return False
        now = time.time()
        models = [GITHUB_MODELS.get(k) for k in ("heavy", "main", "fallback") if GITHUB_MODELS.get(k)]
        return any(now >= self._github_rl_per_model.get(m, 0) for m in models)

    def _github_model_for(self, hint: str) -> str | None:
        """Retorna o modelo GitHub adequado ao tier."""
        now = time.time()

        tier_map = {
            "heavy": GITHUB_MODELS.get("heavy", "DeepSeek-R1"),
            "main": GITHUB_MODELS.get("main", "DeepSeek-V3-0324"),
            "fast": GITHUB_MODELS.get("fast", "DeepSeek-V3-0324"),
        }

        target = tier_map.get(hint, GITHUB_MODELS.get("main", "DeepSeek-V3-0324"))

        ordered = [target]
        for m in [GITHUB_MODELS.get("main"), GITHUB_MODELS.get("fallback")]:
            if m and m not in ordered:
                ordered.append(m)

        for m in ordered:
            if now >= self._github_rl_per_model.get(m, 0):
                return m
        return None

    def _openrouter_available(self) -> bool:
        if not self._openrouter_ok:
            return False
        now = time.time()
        models = [OPENROUTER_MODELS.get(k) for k in ("main", "fallback", "fallback2") if OPENROUTER_MODELS.get(k)]
        return any(now >= self._openrouter_rl_per_model.get(m, 0) for m in models)

    def _openrouter_model_for(self, hint: str) -> str | None:
        now = time.time()
        ordered = [
            OPENROUTER_MODELS.get("main", "deepseek/deepseek-chat-v3-0324"),
            OPENROUTER_MODELS.get("fallback", "deepseek/deepseek-r1"),
            OPENROUTER_MODELS.get("fallback2"),
        ]
        for m in ordered:
            if m and now >= self._openrouter_rl_per_model.get(m, 0):
                return m
        return None

    def _groq_available(self) -> bool:
        return self._groq_ok and time.time() >= self._groq_rl_until

    def _gemini_model_for(self, model_hint: str) -> str:
        """Retorna o modelo Gemini adequado ao tier, respeitando rate limits."""
        now = time.time()

        # Mapeamento de tier para modelos específicos
        tier_map = {
            "heavy": GEMINI_MODELS.get("heavy", "gemini-2.5-flash"),
            "main": GEMINI_MODELS.get("main", "gemini-2.5-flash"),
            "fast": GEMINI_MODELS.get("fast", "gemini-2.5-flash"),
        }

        target = tier_map.get(model_hint, GEMINI_MODELS.get("main", "gemini-2.5-flash"))

        # Lista de fallback ordenada
        ordered = [target]
        for m in [GEMINI_MODELS.get("main"), GEMINI_MODELS.get("fallback"), GEMINI_MODELS.get("fallback2")]:
            if m and m not in ordered:
                ordered.append(m)

        for m in ordered:
            if now >= self._gemini_rl_per_model.get(m, 0):
                return m
        return ordered[0]

    def _groq_model_for(self, model_hint: str) -> str:
        groq_vals = set(GROQ_MODELS.values())
        if model_hint in groq_vals:
            return model_hint
        if model_hint == "heavy" or model_hint == MODELS.get("heavy"):
            return GROQ_MODELS["heavy"]
        if model_hint in ("fast", "basic") or model_hint in (MODELS.get("fast"), MODELS.get("basic")):
            return GROQ_MODELS["fast"]
        return GROQ_MODELS["main"]

    def _resolve_crew_model(self, task_type: str, used_model: str) -> str | None:
        """Se crew ativo, retorna provider/model pro task_type."""
        if not self._crew_enabled:
            return None
        if "/" in used_model:
            return None  # já é um provider/model explícito
        # Mapeia task_type para modelo do crew
        mapped = CREW_MODELS.get(task_type) or CREW_MODELS.get("default")
        if mapped:
            print(f"[CREW] task={task_type} → {mapped}")
            return mapped
        return None

    def set_crew_mode(self, enabled: bool) -> str:
        self._crew_enabled = enabled
        status = "ativado" if enabled else "desativado"
        return f"Crew mode {status}"

    def set_cascade_order(self, order: list[str] | str) -> None:
        """Altera a ordem do cascade em tempo real.
        Aceita lista ou string separada por vírgula.
        Mantém sempre todos os provedores — apenas reordena."""
        if isinstance(order, str):
            order = [p.strip() for p in order.split(",") if p.strip()]
        valid = list(self._cascade.keys())
        reordered = [p for p in order if p in valid]
        for p in valid:
            if p not in reordered:
                reordered.append(p)
        if reordered:
            global CASCADE_ORDER
            CASCADE_ORDER = reordered

    def get_cascade_order(self) -> list[str]:
        return list(CASCADE_ORDER)

    def generate(
        self,
        prompt: str = None,
        task_type: str = "default",
        model: str | None = None,
        stream: bool = False,
        max_retries: int = 2,
        messages: list = None,
        tools: list = None,
    ) -> str | Generator | dict:
        if tools:
            stream = False

        used_model = model or self.model

        # Crew mode: roteia task_type para o melhor modelo
        crew_model = self._resolve_crew_model(task_type, used_model)
        if crew_model:
            used_model = crew_model

        def _sanitize(res):
            import re
            if res is None or not isinstance(res, (str, dict)):
                return res
            if isinstance(res, str):
                return _sanitize_text(res)
            if isinstance(res, dict):
                msg = res.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    msg["content"] = _sanitize_text(msg["content"])
            return res

        def _sanitize_text(text: str) -> str:
            """Remove múltiplos formatos de blocos de raciocínio/pensamento do texto."""
            # Remove <think>...</think> (DeepSeek, Qwen, etc)
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            # Remove <think> sem fechar (modelo truncou)
            text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
            # Remove <analysis>...</analysis>
            text = re.sub(r"<analysis>.*?</analysis>", "", text, flags=re.DOTALL)
            # Remove <reflection>...</reflection>
            text = re.sub(r"<reflection>.*?</reflection>", "", text, flags=re.DOTALL)
            # Remove <reasoning>...</reasoning>
            text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)
            # Remove [Thinking Process]...[/Thinking Process]
            text = re.sub(r"\[Thinking Process\].*?\[/Thinking Process\]", "", text, flags=re.DOTALL)
            # Remove **Thinking**...seguido por linha vazia ou **Response**/etc
            text = re.sub(r"\*\*Thinking\*\*.*?(?=\*\*(?:Response|Answer|Output)\*\*|\n\n)", "", text, flags=re.DOTALL)
            # Remove linhas que começam com "Reasoning:" (com ou sem espaços)
            lines = text.splitlines()
            filtered = [line for line in lines if not line.lstrip().startswith("Reasoning:")]
            text = "\n".join(filtered)
            # Remove linhas vazias extras no início
            text = re.sub(r"^\n+", "", text)
            return text.strip()

        # Suporte a sintaxe "provider/model" — ex: "puter/gpt-5.2" ou "groq"
        if "/" in used_model:
            provider_name, _, model_override = used_model.partition("/")
            provider_name = provider_name.strip()
            model_override = model_override.strip()
            entry = self._cascade.get(provider_name)
            if entry and entry[0]():
                result = entry[2](prompt, task_type, model_override or entry[1](used_model), stream, messages, tools)
                if result is not None:
                    return _sanitize(result)
                print(f"[LLM] Provedor {provider_name} falhou (retornou None). Fazendo fallback para o cascade normal.")
            else:
                print(
                    f"[LLM] Provedor {provider_name} inativo ou indisponível. Fazendo fallback para o cascade normal."
                )

        _start_time = _time.time()
        _global_timeout = 60

        for provider_name in CASCADE_ORDER:
            if _time.time() - _start_time >= _global_timeout:
                break

            entry = self._cascade.get(provider_name)
            if not entry:
                continue

            available_fn, model_for_fn, generate_fn = entry

            if not available_fn():
                continue

            resolved_model = model_for_fn(used_model)
            if not resolved_model:
                continue

            result = generate_fn(prompt, task_type, resolved_model, stream, messages, tools)
            if result is not None:
                return _sanitize(result)

        # Ollama local está desabilitado
        if stream:
            return iter(["[LLM indisponível]"])
        return "[LLM indisponível] - Nenhum provedor cloud configurado. Adicione uma API key no .env (GROQ, GEMINI, MISTRAL, etc.)."

    # ── Gemini ────────────────────────────────────────────────

    def _generate_gemini(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        """Gera com Gemini. Retorna None para fazer fallback."""
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])

        # Converte tools do formato OpenAI para formato Gemini
        gemini_tools = None
        if tools:
            gemini_tools = self._openai_tools_to_gemini(tools)

        # Monta histórico e extrai system instruction + última mensagem do usuário
        history = []
        system_instruction = None
        user_content = prompt or ""

        if messages:
            for msg in messages[:-1]:
                role = msg.get("role", "user")
                content = msg.get("content") or ""

                if role == "system":
                    system_instruction = content
                elif role == "assistant":
                    parts = []
                    if content:
                        parts.append(content)
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        tc_name = fn.get("name", "")
                        args_raw = fn.get("arguments", "{}")
                        if isinstance(args_raw, str):
                            try:
                                args_dict = json.loads(args_raw) if args_raw else {}
                            except json.JSONDecodeError:
                                args_dict = {"raw": args_raw}
                        else:
                            args_dict = args_raw or {}
                        if tc_name:
                            parts.append({"function_call": {"name": tc_name, "args": args_dict}})
                    if parts:
                        history.append({"role": "model", "parts": parts})
                elif role == "user":
                    if content:
                        history.append({"role": "user", "parts": [content]})
                elif role == "tool":
                    fn_name = msg.get("name") or "tool"
                    history.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "function_response": {
                                        "name": fn_name,
                                        "response": {"result": content},
                                    }
                                }
                            ],
                        }
                    )
            # Última mensagem — input atual ou continuação após ferramenta
            last = messages[-1]
            last_role = last.get("role", "user")
            if last_role == "tool":
                fn_name = last.get("name") or "tool"
                history.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "name": fn_name,
                                    "response": {"result": last.get("content") or ""},
                                }
                            }
                        ],
                    }
                )
                user_content = "Responda ao usuário em português com base nos resultados das ferramentas."
            else:
                user_content = last.get("content") or prompt or ""

        try:
            cfg = genai.GenerationConfig(
                temperature=params["temperature"],
                top_p=params["top_p"],
                max_output_tokens=params["max_tokens"],
            )
            client = genai.GenerativeModel(
                model,
                generation_config=cfg,
                system_instruction=system_instruction,
                tools=gemini_tools,
            )

            print(f"[LLM] Usando Gemini: {model} (Task: {task_type})")

            if stream and not tools:
                return self._gemini_stream(client, history, user_content, model, task_type)

            chat = client.start_chat(history=history)
            response = chat.send_message(user_content)

            # Verifica se há function calls na resposta
            tool_calls = []
            for part in response.parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    fc = part.function_call
                    # Converte MapComposite (proto) para dict Python
                    args_dict = {}
                    for k, v in fc.args.items():
                        args_dict[k] = v
                    tool_calls.append(
                        NormalizedToolCall(
                            id=f"gemini_{fc.name}_{int(time.time())}",
                            type="function",
                            function=ToolCallFunction(
                                name=fc.name,
                                arguments=json.dumps(args_dict),
                            ),
                        )
                    )

            if tool_calls:
                return {"tool_calls": tool_calls, "message": response}

            # Resposta de texto
            text = ""
            for part in response.parts:
                if hasattr(part, "text") and part.text:
                    text += part.text
            return text.strip() if text else None

        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                # Marca este modelo específico em rate limit por 5 minutos
                self._gemini_rl_per_model[model] = time.time() + 300
                next_model = self._gemini_model_for(None)
                if next_model == model:
                    # Todos os modelos Gemini em rate limit
                    self._gemini_rl_until = time.time() + 60
                    print(luna_err("GEMINI_QUOTA", "Todos os modelos Gemini em quota — fallback OpenRouter por 60s"))
                else:
                    print(luna_err("GEMINI_QUOTA", f"Gemini {model} quota — tentando {next_model}"))
                    return self._generate_gemini(prompt, task_type, next_model, stream, messages, tools)
            elif "400" in err or "api_key" in err.lower() or "invalid" in err.lower():
                print(luna_err("GEMINI_AUTH_FAILED", "Gemini key inválida — desativando"))
                self._gemini_ok = False
            else:
                print(luna_err("GEMINI_API_ERROR", str(e)))
            return None

    def _openai_tools_to_gemini(self, tools: list) -> list:
        """Converte tools no formato OpenAI para o formato Gemini (function_declarations)."""
        declarations = []
        for tool in tools:
            fn = tool.get("function", {})
            params = fn.get("parameters", {})
            # Remove campos não suportados pelo Gemini
            clean_params = {
                "type": params.get("type", "object"),
                "properties": params.get("properties", {}),
            }
            if "required" in params:
                clean_params["required"] = params["required"]
            # Remove 'default' dos campos (não suportado pelo Gemini)
            for prop in clean_params.get("properties", {}).values():
                prop.pop("default", None)
                prop.pop("enum", None)  # enum pode causar problemas em alguns casos
            declarations.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": clean_params,
                }
            )
        return [{"function_declarations": declarations}]

    def _gemini_stream(self, client, history: list, user_content: str, model: str, task_type: str) -> Generator:
        try:
            chat = client.start_chat(history=history)
            response = chat.send_message(user_content, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                self._gemini_rl_until = time.time() + 60
                print(luna_err("GEMINI_QUOTA", "Gemini rate limit no stream"))
            else:
                print(luna_err("GEMINI_STREAM_ERROR", str(e)))

        # Fallback para GitHub Models no stream
        oai_msgs = []
        for m in history + [{"role": "user", "parts": [user_content]}]:
            oai_msgs.append(
                {
                    "role": "user" if m["role"] == "user" else "assistant",
                    "content": m["parts"][0] if isinstance(m.get("parts"), list) else m.get("content", ""),
                }
            )
        if self._github_available():
            gh_model = self._github_model_for(model)
            gh_headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
            }
            gh_payload = {
                "model": gh_model,
                "messages": oai_msgs,
                "stream": True,
                "temperature": TASK_PARAMS.get(task_type, TASK_PARAMS["default"])["temperature"],
                "max_tokens": min(TASK_PARAMS.get(task_type, TASK_PARAMS["default"])["max_tokens"], 8000),
            }
            yield from self._github_stream(gh_headers, gh_payload, gh_model, task_type, user_content)
            return

        # Fallback para Naga no stream
        if self._naga_available():
            naga_model = self._naga_model_for(model)
            yield from self._generate_naga(user_content, task_type, naga_model, True, oai_msgs)
            return

        # Fallback para Best AI no stream
        if self._bestai_available():
            bestai_model = self._bestai_model_for(model)
            yield from self._generate_bestai(user_content, task_type, bestai_model, True, oai_msgs)
            return

        # Fallback para Groq no stream
        if self._groq_available():
            groq_model = self._groq_model_for(model)
            params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
            yield from self._groq_stream(oai_msgs, groq_model, params, prompt=user_content, task_type=task_type)
            return

        # Ollama local desabilitado
        yield "[LLM indisponível] - Nenhum provedor stream disponível."

    # ── GitHub Models (DeepSeek V3 / R1) ──────────────────────

    def _generate_github(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 4000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando GitHub Models: {model} (Task: {task_type})")
            if stream:
                return self._github_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{GITHUB_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 413:
                if tools:
                    print(f"[LLM] ⚠ GitHub {model} 413 (payload grande) — tentando sem tools")
                    return self._generate_github(prompt, task_type, model, stream, messages, tools=None)
                print(f"[LLM] ⚠ GitHub {model} 413 — fallback Naga")
                return None
            if resp.status_code == 429:
                self._github_rl_per_model[model] = time.time() + 60
                next_model = self._github_model_for(None)
                if next_model and next_model != model:
                    print(f"[LLM] ⚠ GitHub {model} 429 — tentando {next_model}")
                    payload["model"] = next_model
                    return self._generate_github(prompt, task_type, next_model, stream, messages, tools)
                print("[LLM] ⚠ GitHub todos os modelos 429 — fallback Naga")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._github_rl_per_model[model] = time.time() + 60
                print(f"[LLM] ⚠ GitHub {model} 429 — fallback Naga")
            elif "401" in err or "403" in err:
                print(luna_err("GH_AUTH_FAILED", "GitHub Token inválida — desativando"))
                self._github_ok = False
            else:
                print(f"[LLM] ⚠ GitHub {model} erro: {e} — fallback Naga")
            return None

    def _github_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{GITHUB_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._github_rl_per_model[model] = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ GitHub stream erro: {e} — fallback Naga")
            yield from self._generate_naga(
                prompt,
                task_type,
                self._naga_model_for(model),
                False,
                payload.get("messages"),
                None,
            )

    # ── OpenRouter (DeepSeek V3 / R1) ──────────────────────────

    def _generate_openrouter(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando OpenRouter: {model} (Task: {task_type})")
            if stream:
                return self._openrouter_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._openrouter_rl_per_model[model] = time.time() + 60
                next_model = self._openrouter_model_for(None)
                if next_model and next_model != model:
                    print(f"[LLM] ⚠ OpenRouter {model} 429 — tentando {next_model}")
                    payload["model"] = next_model
                    return self._generate_openrouter(prompt, task_type, next_model, stream, messages, tools)
                print("[LLM] ⚠ OpenRouter todos os modelos 429 — fallback GitHub")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._openrouter_rl_per_model[model] = time.time() + 60
                print(f"[LLM] ⚠ OpenRouter {model} 429 — fallback GitHub")
            elif "402" in err:
                print(luna_err("OR_NO_CREDITS", f"OpenRouter {model} 402 (sem créditos) — fallback GitHub"))
                return None
            elif "401" in err or "403" in err:
                print(luna_err("OR_AUTH_FAILED", "OpenRouter key inválida — desativando"))
                self._openrouter_ok = False
            else:
                print(f"[LLM] ⚠ OpenRouter {model} erro: {e} — fallback GitHub")
            return None

    def _openrouter_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._openrouter_rl_per_model[model] = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ OpenRouter stream erro: {e} — fallback GitHub")
            yield from self._generate_github(
                prompt,
                task_type,
                self._github_model_for(model),
                False,
                payload.get("messages"),
                None,
            )

    # ── Chutes.ai (DeepSeek-V3.2-TEE, Qwen3.6) ─────────────────

    def _chutes_available(self) -> bool:
        return self._chutes_ok and time.time() >= self._chutes_rl_until

    def _chutes_model_for(self, hint: str) -> str:
        ordered = [
            CHUTES_MODELS.get("main"),
            CHUTES_MODELS.get("heavy"),
            CHUTES_MODELS.get("fast"),
            CHUTES_MODELS.get("fallback"),
        ]
        return next((m for m in ordered if m), "deepseek-ai/DeepSeek-V3.2-TEE")

    def _generate_chutes(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {CHUTES_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando Chutes.ai: {model} (Task: {task_type})")
            if stream:
                return self._chutes_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{CHUTES_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._chutes_rl_until = time.time() + 60
                print("[LLM] ⚠ Chutes.ai 429 — fallback GitHub por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._chutes_rl_until = time.time() + 60
                print("[LLM] ⚠ Chutes.ai 429 — fallback GitHub")
            elif "401" in err or "403" in err:
                print(luna_err("CHUTES_AUTH_FAILED", "Chutes.ai key inválida — desativando"))
                self._chutes_ok = False
            else:
                print(f"[LLM] ⚠ Chutes.ai erro: {e} — fallback GitHub")
            return None

    def _chutes_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{CHUTES_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._chutes_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ Chutes.ai stream erro: {e} — fallback GitHub")
            yield from self._generate_github(
                prompt,
                task_type,
                self._github_model_for(model),
                False,
                payload.get("messages"),
                None,
            )

    # ── Naga AI (Nemotron, Llama gratuitos) ──────────────────

    def _naga_available(self) -> bool:
        return self._naga_ok and time.time() >= self._naga_rl_until

    def _naga_model_for(self, hint: str) -> str:
        ordered = [
            NAGA_MODELS.get("main"),
            NAGA_MODELS.get("heavy"),
            NAGA_MODELS.get("fast"),
            NAGA_MODELS.get("fallback"),
        ]
        return next((m for m in ordered if m), "nemotron-3-super-120b-a12b:free")

    def _generate_naga(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {NAGA_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando Naga AI: {model} (Task: {task_type})")
            if stream:
                return self._naga_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{NAGA_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._naga_rl_until = time.time() + 60
                print("[LLM] ⚠ Naga AI 429 — fallback Best AI por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._naga_rl_until = time.time() + 60
                print("[LLM] ⚠ Naga AI 429 — fallback Best AI")
            elif "401" in err or "403" in err:
                print(luna_err("NAGA_AUTH_FAILED", "Naga AI key inválida — desativando"))
                self._naga_ok = False
            else:
                print(f"[LLM] ⚠ Naga AI erro: {e} — fallback Best AI")
            return None

    def _naga_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{NAGA_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._naga_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ Naga stream erro: {e} — fallback Best AI")
            yield from self._generate_bestai(
                prompt,
                task_type,
                self._bestai_model_for(model),
                False,
                payload.get("messages"),
                None,
            )

    # ── Best AI (DeepSeek, Qwen, Gemini gratuitos) ────────────

    def _bestai_available(self) -> bool:
        return self._bestai_ok and time.time() >= self._bestai_rl_until

    def _bestai_model_for(self, hint: str) -> str:
        ordered = [
            BESTAI_MODELS.get("main"),
            BESTAI_MODELS.get("heavy"),
            BESTAI_MODELS.get("fast"),
            BESTAI_MODELS.get("fallback"),
        ]
        return next((m for m in ordered if m), "deepseek-v3.1")

    def _generate_bestai(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {BESTAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando Best AI: {model} (Task: {task_type})")
            if stream:
                return self._bestai_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{BESTAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._bestai_rl_until = time.time() + 60
                print("[LLM] ⚠ Best AI 429 — fallback Groq por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._bestai_rl_until = time.time() + 60
                print("[LLM] ⚠ Best AI 429 — fallback Groq")
            elif "401" in err or "403" in err:
                print(luna_err("BESTAI_AUTH_FAILED", "Best AI key inválida — desativando"))
                self._bestai_ok = False
            else:
                print(f"[LLM] ⚠ Best AI erro: {e} — fallback Groq")
            return None

    def _bestai_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{BESTAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._bestai_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ Best AI stream erro: {e} — fallback Groq")
            yield from self._groq_stream(
                payload.get("messages", [{"role": "user", "content": prompt}]),
                self._groq_model_for(model),
                TASK_PARAMS.get(task_type, TASK_PARAMS["default"]),
                prompt=prompt,
                task_type=task_type,
            )

    # ── Completions.me (gratuito, ilimitado) ───────────────────

    def _completions_available(self) -> bool:
        return self._completions_ok and time.time() >= self._completions_rl_until

    def _completions_model_for(self, hint: str) -> str | None:
        ordered = [
            COMPLETIONS_MODELS.get("main"),
            COMPLETIONS_MODELS.get("heavy"),
            COMPLETIONS_MODELS.get("fast"),
            COMPLETIONS_MODELS.get("fallback"),
            COMPLETIONS_MODELS.get("fallback2"),
        ]
        return next((m for m in ordered if m), None)

    def _generate_completions(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {COMPLETIONS_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando Completions.me: {model} (Task: {task_type})")
            if stream:
                return self._completions_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{COMPLETIONS_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._completions_rl_until = time.time() + 60
                print("[LLM] ⚠ Completions.me 429 — fallback Chutes.ai por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._completions_rl_until = time.time() + 60
                print("[LLM] ⚠ Completions.me 429 — fallback Chutes.ai")
            elif "401" in err or "403" in err:
                print(luna_err("COMPLETIONS_AUTH_FAILED", "Completions.me key inválida — desativando"))
                self._completions_ok = False
            else:
                print(f"[LLM] ⚠ Completions.me erro: {e} — fallback Chutes.ai")
            return None

    def _completions_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{COMPLETIONS_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._completions_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ Completions.me stream erro: {e} — fallback Chutes.ai")
            yield from self._generate_chutes(
                prompt,
                task_type,
                self._chutes_model_for(model),
                False,
                payload.get("messages"),
                None,
            )

    # ── FreeTheAi ─────────────────────────────────────────────

    def _freetheai_available(self) -> bool:
        return self._freetheai_ok and time.time() >= self._freetheai_rl_until

    def _freetheai_model_for(self, hint: str) -> str | None:
        ordered = [
            FREETHEAI_MODELS.get("main"),
            FREETHEAI_MODELS.get("heavy"),
            FREETHEAI_MODELS.get("fast"),
            FREETHEAI_MODELS.get("fallback"),
        ]
        return next((m for m in ordered if m), None)

    def _generate_freetheai(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {FREETHEAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": req_msgs,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 32000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            print(f"[LLM] Usando FreeTheAi: {model} (Task: {task_type})")
            if stream:
                return self._freetheai_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{FREETHEAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._freetheai_rl_until = time.time() + 60
                print("[LLM] ⚠ FreeTheAi 429 — rate limit por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            return (msg.get("content") or "").strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._freetheai_rl_until = time.time() + 60
                print("[LLM] ⚠ FreeTheAi 429 — fallback")
            elif "401" in err or "403" in err:
                print(luna_err("FREETHEAI_AUTH_FAILED", "FreeTheAi key inválida — desativando"))
                self._freetheai_ok = False
            else:
                print(f"[LLM] ⚠ FreeTheAi erro: {e} — fallback")
            return None

    def _freetheai_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{FREETHEAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._freetheai_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                yield from _parse_sse_stream(resp)
            return
        except Exception as e:
            print(f"[LLM] ⚠ FreeTheAi stream erro: {e} — fallback")
            yield from []

    # ── Puter LLM (gpt-5, o3, gpt-4o, gpt-4o-mini) ──────────

    def _puter_available(self) -> bool:
        return self._puter_ok and time.time() >= self._puter_rl_until

    def _puter_model_for(self, hint: str) -> str:
        ordered = [
            PUTER_LLM_MODELS.get("heavy"),
            PUTER_LLM_MODELS.get("main"),
            PUTER_LLM_MODELS.get("fast"),
        ]
        return next((m for m in ordered if m), "gpt-4o-mini")

    def _generate_puter(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        headers = {
            "Authorization": f"Bearer {PUTER_TOKEN}",
            "Content-Type": "application/json",
        }
        args = {
            "messages": req_msgs,
            "model": model,
            "temperature": params["temperature"],
            "max_tokens": min(params["max_tokens"], 16000),
            "top_p": params["top_p"],
            "stream": stream,
        }
        if tools and not stream:
            args["tools"] = tools
            args["tool_choice"] = "auto"

        payload = {
            "interface": "puter-chat-completion",
            "provider": "openai-completion",
            "method": "complete",
            "args": args,
        }

        try:
            print(f"[LLM] Usando Puter: {model} (Task: {task_type})")
            if stream:
                return self._puter_stream(headers, payload, model, task_type, prompt)

            resp = self._session.post(
                f"{PUTER_API_BASE_URL}/drivers/call",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if resp.status_code == 429:
                self._puter_rl_until = time.time() + 60
                print("[LLM] ⚠ Puter 429 — rate limit por 60s")
                return None
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            msg = result.get("message", {})
            raw_tcs = msg.get("tool_calls")
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": msg}
            raw = msg.get("content") or ""
            if isinstance(raw, list):
                texts = [b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text"]
                raw = " ".join(texts)
            return str(raw).strip() or None

        except Exception as e:
            err = str(e)
            if "429" in err:
                self._puter_rl_until = time.time() + 60
                print("[LLM] ⚠ Puter 429 — rate limit por 60s")
            elif "402" in err:
                print("[LLM] ⚠ Puter 402 (sem cota) — fallback silencioso")
                self._puter_rl_until = time.time() + 120
            elif "401" in err or "403" in err:
                print(luna_err("PUTER_AUTH_FAILED", "Puter token inválido — desativando"))
                self._puter_ok = False
            elif "500" in err or "503" in err:
                print(f"[LLM] ⚠ Puter erro servidor: {e} — fallback")
            else:
                print(f"[LLM] ⚠ Puter erro: {e} — fallback")
            return None

    def _puter_stream(self, headers: dict, payload: dict, model: str, task_type: str, prompt: str) -> Generator:
        try:
            with self._session.post(
                f"{PUTER_API_BASE_URL}/drivers/call",
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code == 429:
                    self._puter_rl_until = time.time() + 60
                    raise Exception("429")
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8") if isinstance(line, bytes) else line
                    try:
                        chunk = json.loads(line)
                        if chunk.get("type") == "text":
                            yield chunk.get("text", "")
                        elif chunk.get("type") == "usage":
                            pass
                    except Exception:
                        continue
            return
        except Exception as e:
            print(f"[LLM] ⚠ Puter stream erro: {e} — fallback")
            yield from []

    # ── Groq ──────────────────────────────────────────────────

    def _generate_groq(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]

        try:
            if stream:
                return self._groq_stream(req_msgs, model, params, prompt=prompt, task_type=task_type)

            print(f"[LLM] Usando Groq: {model} (Task: {task_type})")
            kwargs = {
                "model": model,
                "messages": req_msgs,
                "temperature": params["temperature"],
                "max_tokens": params["max_tokens"],
                "top_p": params["top_p"],
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            completion = self._groq.chat.completions.create(**kwargs)
            raw_tcs = completion.choices[0].message.tool_calls
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": completion.choices[0].message}
            return completion.choices[0].message.content.strip()

        except Exception as e:
            err = str(e)
            if "429" in err or "413" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
                if "413" in err and tools:
                    print(
                        luna_err(
                            "GROQ_RATE_LIMIT",
                            "Groq TPM Limit excedido com ferramentas. Tentando sem ferramentas (modo fallback seguro)...",
                        )
                    )
                    return self._generate_groq(prompt, task_type, model, stream, messages, tools=None)
                self._groq_rl_until = time.time() + 60
                print(luna_err("GROQ_RATE_LIMIT", "Groq rate limit — fallback Ollama por 60s"))
            elif "401" in err or "authentication" in err.lower():
                print(luna_err("GROQ_AUTH_FAILED", "Groq key inválida — desativando"))
                self._groq_ok = False
            else:
                print(luna_err("GROQ_API_ERROR", str(e)))
            return None

    def _groq_stream(
        self, messages: list, model: str, params: dict, prompt: str = None, task_type: str = "default"
    ) -> Generator:
        try:
            print(f"[LLM] Groq stream: {model}")
            stream = self._groq.chat.completions.create(
                model=model,
                messages=messages,
                temperature=params["temperature"],
                max_tokens=params["max_tokens"],
                top_p=params["top_p"],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return
        except Exception as e:
            err = str(e)
            if "429" in err or "413" in err or "rate_limit" in err.lower():
                self._groq_rl_until = time.time() + 60
                print(luna_err("GROQ_RATE_LIMIT", "Groq rate limit no stream"))
            else:
                print(luna_err("GROQ_API_ERROR", f"Stream: {e}"))

        yield "[LLM indisponível] - Nenhum provedor cloud disponível para stream."

    def classify(self, text: str, categories: list[str]) -> str:
        cats = ", ".join(f'"{c}"' for c in categories)
        prompt = (
            f"Classifique o texto abaixo em UMA das categorias: {cats}\n"
            f"Responda APENAS com a categoria, sem explicações.\n\n"
            f"Texto: {text}\nCategoria:"
        )
        result = self.generate(prompt, task_type="command", model=MODELS.get("fast", self.model))
        result = result.strip().strip('"').strip("'").lower()
        for cat in categories:
            if cat.lower() in result:
                return cat
        return categories[0]

    # ── Mistral ───────────────────────────────────────────────

    def _generate_mistral(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> str | Generator | dict | None:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        try:
            if stream:
                return self._mistral_stream(req_msgs, model, params, prompt=prompt, task_type=task_type)

            print(f"[LLM] Usando Mistral AI: {model} (Task: {task_type})")
            kwargs = {
                "model": model,
                "messages": req_msgs,
                "temperature": params["temperature"],
                "max_tokens": params["max_tokens"],
                "top_p": params["top_p"],
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            completion = self._mistral_client.chat.complete(**kwargs)
            raw_tcs = completion.choices[0].message.tool_calls
            if raw_tcs:
                return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": completion.choices[0].message}
            return completion.choices[0].message.content.strip()

        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                self._mistral_rl_until = time.time() + 60
                print(luna_err("MISTRAL_QUOTA", "Mistral rate limit — fallback Gemini por 60s"))
            elif "401" in err or "authentication" in err.lower():
                print(luna_err("MISTRAL_AUTH_FAILED", "Mistral key inválida — desativando"))
                self._mistral_ok = False
            else:
                print(luna_err("MISTRAL_API_ERROR", str(e)))
            return None

    def _mistral_stream(
        self, messages: list, model: str, params: dict, prompt: str = None, task_type: str = "default"
    ) -> Generator:
        try:
            print(f"[LLM] Mistral stream: {model}")
            stream_resp = self._mistral_client.chat.stream(
                model=model,
                messages=messages,
                temperature=params["temperature"],
                max_tokens=params["max_tokens"],
                top_p=params["top_p"],
            )
            for chunk in stream_resp:
                delta = chunk.data.choices[0].delta.content
                if delta:
                    yield delta
            return
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                self._mistral_rl_until = time.time() + 60
                print(luna_err("MISTRAL_QUOTA", "Mistral rate limit no stream"))
            else:
                print(luna_err("MISTRAL_API_ERROR", f"Stream: {e}"))

        gemini_model = self._gemini_model_for(model)
        if self._gemini_available():
            yield from self._generate_gemini(
                prompt=prompt,
                task_type=task_type,
                model=gemini_model,
                stream=True,
                messages=messages,
            )

    def get_providers_status(self) -> list[dict]:
        now = time.time()

        def rl(t):
            return round(max(0, t - now), 1) if t > now else 0

        def model_for(mod_dict, hint="main"):
            return mod_dict.get(hint, mod_dict.get("main", "?")) if mod_dict else "?"

        return [
            {
                "name": "Mistral",
                "active": self._mistral_ok,
                "available": self._mistral_available(),
                "rate_limited_for": rl(self._mistral_rl_until),
                "model": model_for(globals().get("MISTRAL_MODELS")),
            },
            {
                "name": "Gemini",
                "active": self._gemini_ok,
                "available": self._gemini_available(),
                "rate_limited_for": rl(self._gemini_rl_until),
                "models": {
                    k: {"name": v, "rate_limited_for": rl(self._gemini_rl_per_model.get(v, 0))}
                    for k, v in (globals().get("GEMINI_MODELS") or {}).items()
                },
            },
            {
                "name": "OpenRouter",
                "active": self._openrouter_ok,
                "available": self._openrouter_available(),
                "rate_limited_for": 0,
                "models": {
                    k: {"name": v, "rate_limited_for": rl(self._openrouter_rl_per_model.get(v, 0))}
                    for k, v in (globals().get("OPENROUTER_MODELS") or {}).items()
                },
            },
            {
                "name": "Completions.me",
                "active": self._completions_ok,
                "available": self._completions_available(),
                "rate_limited_for": rl(self._completions_rl_until),
                "models": {
                    k: {"name": v, "rate_limited_for": 0}
                    for k, v in (globals().get("COMPLETIONS_MODELS") or {}).items()
                },
            },
            {
                "name": "Chutes.ai",
                "active": self._chutes_ok,
                "available": self._chutes_available(),
                "rate_limited_for": rl(self._chutes_rl_until),
                "model": model_for(globals().get("CHUTES_MODELS")),
            },
            {
                "name": "GitHub Models",
                "active": self._github_ok,
                "available": self._github_available(),
                "rate_limited_for": 0,
                "models": {
                    k: {"name": v, "rate_limited_for": rl(self._github_rl_per_model.get(v, 0))}
                    for k, v in (globals().get("GITHUB_MODELS") or {}).items()
                },
            },
            {
                "name": "Naga AI",
                "active": self._naga_ok,
                "available": self._naga_available(),
                "rate_limited_for": rl(self._naga_rl_until),
                "model": model_for(globals().get("NAGA_MODELS")),
            },
            {
                "name": "Best AI",
                "active": self._bestai_ok,
                "available": self._bestai_available(),
                "rate_limited_for": rl(self._bestai_rl_until),
                "model": model_for(globals().get("BESTAI_MODELS")),
            },
            {
                "name": "Groq",
                "active": self._groq_ok,
                "available": self._groq_available(),
                "rate_limited_for": rl(self._groq_rl_until),
                "model": model_for(globals().get("GROQ_MODELS")),
            },
            {
                "name": "FreeTheAi",
                "active": self._freetheai_ok,
                "available": self._freetheai_available(),
                "rate_limited_for": rl(self._freetheai_rl_until),
                "models": {
                    k: {"name": v, "rate_limited_for": 0} for k, v in (globals().get("FREETHEAI_MODELS") or {}).items()
                },
            },
            {
                "name": "Puter",
                "active": self._puter_ok,
                "available": self._puter_available(),
                "rate_limited_for": rl(self._puter_rl_until),
                "models": {
                    k: {"name": v, "rate_limited_for": 0} for k, v in (globals().get("PUTER_LLM_MODELS") or {}).items()
                },
            },
        ]

    def is_ready(self) -> bool:
        return self.available

    def supports_native_tools(self) -> bool:
        """Provedores com function calling confiável (Ollama local excluído)."""
        return (
            self._mistral_available()
            or self._gemini_available()
            or self._completions_available()
            or self._github_available()
            or self._naga_available()
            or self._bestai_available()
            or self._freetheai_available()
            or self._groq_available()
        )

    def build_langchain_llm(self, provider: str, temperature: float = 0.3):
        """Cria um Chat model do LangChain apontando pro provedor especificado."""
        provider = provider.lower()
        try:
            if provider == "groq":
                from langchain_groq import ChatGroq

                model = GROQ_MODELS.get("main", "qwen/qwen3-32b")
                if GROQ_API_KEY:
                    return ChatGroq(groq_api_key=GROQ_API_KEY, model_name=model, temperature=temperature)
            elif provider == "completions":
                from langchain_openai import ChatOpenAI

                model = COMPLETIONS_MODELS.get("main", "claude-sonnet-4.6")
                if COMPLETIONS_API_KEY:
                    return ChatOpenAI(
                        api_key=COMPLETIONS_API_KEY, model=model, base_url=COMPLETIONS_BASE_URL, temperature=temperature
                    )
            elif provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI

                model = GEMINI_MODELS.get("main", "gemini-2.5-flash")
                if GEMINI_API_KEY:
                    return ChatGoogleGenerativeAI(api_key=GEMINI_API_KEY, model=model, temperature=temperature)
            elif provider == "openrouter":
                from langchain_openai import ChatOpenAI

                model = OPENROUTER_MODELS.get("main", "deepseek/deepseek-chat-v3-0324")
                if OPENROUTER_API_KEY:
                    return ChatOpenAI(
                        api_key=OPENROUTER_API_KEY, model=model, base_url=OPENROUTER_BASE_URL, temperature=temperature
                    )
            elif provider == "mistral":
                from langchain_mistralai import ChatMistralAI

                model = MISTRAL_MODELS.get("main", "mistral-large-latest")
                if MISTRAL_API_KEY:
                    return ChatMistralAI(api_key=MISTRAL_API_KEY, model=model, temperature=temperature)
            elif provider == "github":
                from langchain_openai import ChatOpenAI

                model = GITHUB_MODELS.get("main", "DeepSeek-V3-0324")
                if GITHUB_TOKEN:
                    return ChatOpenAI(
                        api_key=GITHUB_TOKEN, model=model, base_url=GITHUB_BASE_URL, temperature=temperature
                    )
            elif provider == "naga":
                from langchain_openai import ChatOpenAI

                model = NAGA_MODELS.get("main", "nemotron-3-super-120b-a12b:free")
                if NAGA_API_KEY:
                    return ChatOpenAI(
                        api_key=NAGA_API_KEY, model=model, base_url=NAGA_BASE_URL, temperature=temperature
                    )
            elif provider == "bestai":
                from langchain_openai import ChatOpenAI

                model = BESTAI_MODELS.get("main", "deepseek-v3.1")
                if BESTAI_API_KEY:
                    return ChatOpenAI(
                        api_key=BESTAI_API_KEY, model=model, base_url=BESTAI_BASE_URL, temperature=temperature
                    )
            elif provider == "freetheai":
                from langchain_openai import ChatOpenAI

                model = FREETHEAI_MODELS.get("main", "glm/glm-5.1")
                if FREETHEAI_API_KEY:
                    return ChatOpenAI(
                        api_key=FREETHEAI_API_KEY, model=model, base_url=FREETHEAI_BASE_URL, temperature=temperature
                    )
        except ImportError as e:
            print(f"[LLM] ⚠ langchain lib não disponível para {provider}: {e}")
        except Exception as e:
            print(f"[LLM] ⚠ Erro ao criar ChatLangChain para {provider}: {e}")
        return None


# Singleton
_llm_instance: LLMWrapper | None = None


def get_llm() -> LLMWrapper:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMWrapper()
    return _llm_instance
