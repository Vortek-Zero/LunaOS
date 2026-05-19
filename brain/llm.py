#!/usr/bin/env python3
"""
brain/llm.py — LLM híbrido: Groq (primário) + Ollama (fallback automático)

Prioridade:
  1. Groq API  → llama-3.3-70b / llama-3.1-8b  (online, rápido)
  2. Ollama    → qwen2.5:7b / 3b / 0.5b         (local, fallback automático)

Fallback ativado em:
  - Rate limit Groq (429)
  - Groq offline / sem key
  - Erro de conexão com Groq
"""
import json
import time
import os
from typing import Optional, Generator, Union
from dataclasses import dataclass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

try:
    from groq import Groq as GroqClient
    HAS_GROQ_LIB = True
except ImportError:
    HAS_GROQ_LIB = False

try:
    from config import (
        OLLAMA_GENERATE_URL as OLLAMA_URL,
        OLLAMA_TAGS_URL,
        MODELS,
        MODEL_TIMEOUTS,
        GROQ_API_KEY,
        GROQ_MODELS,
    )
except ImportError:
    OLLAMA_URL      = "http://localhost:11434/api/generate"
    OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
    MODELS = {
        "heavy": "qwen2.5:7b-instruct-q4_K_M",
        "main":  "qwen2.5:3b",
        "fast":  "qwen2.5:0.5b-instruct-fp16",
        "basic": "qwen2.5:0.5b",
    }
    MODEL_TIMEOUTS = {"fast": 30, "main": 120, "heavy": 600}
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODELS = {
        "heavy": "qwen/qwen3-32b",
        "main":  "llama-3.3-70b-versatile",
        "fast":  "llama-3.1-8b-instant",
    }


@dataclass
class ToolCallFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class NormalizedToolCall:
    """Representação unificada de tool_call para Groq e Ollama."""
    id: str
    type: str
    function: ToolCallFunction


def _normalize_tool_calls(raw_tool_calls) -> list:
    """
    Converte tool_calls de Groq (objetos) ou Ollama (dicts) para NormalizedToolCall.
    Retorna lista vazia se a entrada for inválida.
    """
    if not raw_tool_calls:
        return []
    result = []
    for tc in raw_tool_calls:
        try:
            if isinstance(tc, dict):
                # Formato Ollama
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                result.append(NormalizedToolCall(
                    id=tc.get("id", f"call_{len(result)}"),
                    type=tc.get("type", "function"),
                    function=ToolCallFunction(
                        name=fn.get("name", ""),
                        arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                    ),
                ))
            else:
                # Formato Groq (objeto com atributos)
                fn = tc.function
                result.append(NormalizedToolCall(
                    id=getattr(tc, "id", f"call_{len(result)}"),
                    type=getattr(tc, "type", "function"),
                    function=ToolCallFunction(
                        name=fn.name,
                        arguments=fn.arguments,
                    ),
                ))
        except Exception as e:
            print(f"[LLM] ⚠ Erro ao normalizar tool_call: {e}")
    return result

# ── Parâmetros por tipo de tarefa ─────────────────────────────
TASK_PARAMS = {
    "factual":        {"temperature": 0.05, "top_p": 0.85, "max_tokens": 500},
    "creative":       {"temperature": 0.85, "top_p": 0.95, "max_tokens": 3000},
    "command":        {"temperature": 0.1,  "top_p": 0.90, "max_tokens": 200},
    "planning":       {"temperature": 0.15, "top_p": 0.90, "max_tokens": 500},
    "coding":         {"temperature": 0.1,  "top_p": 0.90, "max_tokens": 4000},
    "conversational": {"temperature": 0.70, "top_p": 0.95, "max_tokens": 1500},
    "default":        {"temperature": 0.2,  "top_p": 0.90, "max_tokens": 500},
}

# Parâmetros Ollama (usa num_predict em vez de max_tokens)
def _ollama_params(task_type: str) -> dict:
    p = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
    return {
        "temperature":    p["temperature"],
        "top_p":          p["top_p"],
        "num_predict":    p["max_tokens"],
        "top_k":          40,
        "repeat_penalty": 1.1,
    }


# ── Mapeamento Ollama model → tier ───────────────────────────
def _ollama_model_for_tier(groq_model: str) -> str:
    """Dado um modelo Groq, retorna o equivalente Ollama."""
    if groq_model == GROQ_MODELS.get("heavy"):
        return MODELS["heavy"]
    elif groq_model in (GROQ_MODELS.get("main"), GROQ_MODELS.get("fast")):
        return MODELS["main"]
    return MODELS["main"]


class LLMWrapper:
    """
    Interface unificada de LLM.
    - Usa Groq quando disponível
    - Fallback automático para Ollama em rate limit (429) ou falha
    - Transparente para o resto do sistema
    """

    def __init__(self, model: str = None):
        self.model = model or MODELS["main"]
        self.available = False
        self._stop_flag = False

        # Estado do Groq
        self._groq_ok  = HAS_GROQ_LIB and bool(GROQ_API_KEY)
        self._groq_rl_until = 0.0   # timestamp até quando o rate limit está ativo

        # Ollama session
        if HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        else:
            self._session = None

        # Inicializa Groq client
        if self._groq_ok:
            try:
                self._groq = GroqClient(api_key=GROQ_API_KEY)
                print("[LLM] ✓ Groq API ativo (llama-3.3-70b / llama-3.1-8b-instant)")
                self.available = True
            except Exception as e:
                print(f"[LLM] ⚠ Groq não inicializou: {e}")
                self._groq_ok = False

        # Checa Ollama (sempre, para ter fallback)
        self._ollama_ok = self._check_ollama()
        if not self.available:
            self.available = self._ollama_ok

    def _check_ollama(self) -> bool:
        try:
            if self._session:
                resp = self._session.get(OLLAMA_TAGS_URL, timeout=3)
                ok = resp.status_code == 200
            else:
                req = urllib.request.Request(OLLAMA_TAGS_URL)
                with urllib.request.urlopen(req, timeout=3) as resp:
                    ok = resp.status == 200
            if ok:
                print("[LLM] ✓ Ollama disponível (fallback local)")
            return ok
        except Exception:
            return False

    def _groq_rate_limited(self) -> bool:
        """Retorna True se ainda estamos em rate limit do Groq."""
        return time.time() < self._groq_rl_until

    def _use_groq(self, task_type: str = "default") -> bool:
        # Groq é usado para todos os tipos de tarefa, incluindo coding.
        # O limite gratuito é gerenciado pelo rate-limit automático (fallback para Ollama se 429).
        return self._groq_ok and not self._groq_rate_limited()

    def _groq_model_for(self, ollama_model: str) -> str:
        """Mapeia modelo Ollama para o equivalente Groq. Se já for um modelo Groq, retorna direto."""
        groq_model_values = set(GROQ_MODELS.values())
        if ollama_model in groq_model_values:
            return ollama_model  # já é um modelo Groq
        if ollama_model == MODELS.get("heavy"):
            return GROQ_MODELS["heavy"]
        elif ollama_model in (MODELS.get("main"), MODELS.get("basic")):
            return GROQ_MODELS["main"]
        elif ollama_model == MODELS.get("fast"):
            return GROQ_MODELS["fast"]
        return GROQ_MODELS["main"]

    def generate(
        self,
        prompt: str = None,
        task_type: str = "default",
        model: Optional[str] = None,
        stream: bool = False,
        max_retries: int = 2,
        messages: list = None,
        tools: list = None
    ) -> Union[str, Generator, dict]:

        if tools:
            stream = False

        if not self.available:
            if not self._check_ollama():
                return "" if not stream else iter([""])

        used_model = model or self.model

        # ── Tenta Groq primeiro ───────────────────────────────
        if self._use_groq(task_type):
            groq_model = self._groq_model_for(used_model)
            result = self._generate_groq(prompt, task_type, groq_model, stream, messages, tools)
            if result is not None:
                return result

        # ── Fallback Ollama ───────────────────────────────────
        # Se used_model é um modelo Groq, converte para o equivalente Ollama
        ollama_model = _ollama_model_for_tier(used_model) if used_model in set(GROQ_MODELS.values()) else used_model
        if self._ollama_ok or self._check_ollama():
            self._ollama_ok = True
            return self._generate_ollama(prompt, task_type, ollama_model, stream, max_retries, messages, tools)

        return "" if not stream else iter(["[LLM indisponível]"])

    # ── Groq ──────────────────────────────────────────────────

    def _generate_groq(
        self, prompt: str, task_type: str, model: str, stream: bool, messages: list = None, tools: list = None
    ) -> Optional[Union[str, Generator, dict]]:
        """Gera com Groq. Retorna None se deve fazer fallback."""
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        try:
            if stream:
                return self._groq_stream(req_msgs, model, params, prompt=prompt, task_type=task_type, ollama_model=_ollama_model_for_tier(model))

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
                normalized = _normalize_tool_calls(raw_tcs)
                return {"tool_calls": normalized, "message": completion.choices[0].message}
                
            return completion.choices[0].message.content.strip()

        except Exception as e:
            err = str(e)
            if "429" in err or "413" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
                # Tenta 1 retry rápido antes de cair no fallback
                time.sleep(0.5)
                try:
                    completion = self._groq.chat.completions.create(**kwargs)
                    raw_tcs = completion.choices[0].message.tool_calls
                    if raw_tcs:
                        return {"tool_calls": _normalize_tool_calls(raw_tcs), "message": completion.choices[0].message}
                    return completion.choices[0].message.content.strip()
                except Exception:
                    pass
                self._groq_rl_until = time.time() + 60
                print(f"[LLM] ⚠ Groq rate limit (ou 413) — fallback Ollama por 60s")
            elif "401" in err or "authentication" in err.lower():
                print(f"[LLM] ⚠ Groq key inválida — desativando Groq")
                self._groq_ok = False
            else:
                print(f"[LLM] ⚠ Groq erro: {e} — tentando Ollama")
            return None

    def _groq_stream(self, messages: list, model: str, params: dict, prompt: str = None, task_type: str = "coding", ollama_model: str = None) -> Generator:
        """Stream do Groq com fallback transparente para Ollama se falhar."""
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
            return  # stream concluído com sucesso
        except Exception as e:
            err = str(e)
            if "429" in err or "413" in err or "rate_limit" in err.lower():
                self._groq_rl_until = time.time() + 60
                print("[LLM] ⚠ Groq rate limit no stream — fallback Ollama")
            else:
                print(f"[LLM] ⚠ Groq stream erro: {e} — fallback Ollama")

        # Fallback: delega para Ollama em vez de retornar string de erro
        fallback_model = ollama_model or _ollama_model_for_tier(model)
        print(f"[LLM] Groq stream fallback → Ollama: {fallback_model}")
        yield from self._generate_ollama(
            prompt=prompt,
            task_type=task_type,
            model=fallback_model,
            stream=True,
            max_retries=1,
            messages=messages,
        )

    # ── Ollama ────────────────────────────────────────────────

    def _generate_ollama(
        self, prompt: str, task_type: str, model: str, stream: bool, max_retries: int, messages: list = None, tools: list = None
    ) -> Union[str, Generator, dict]:
        params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
        print(f"[LLM] Usando Ollama: {model} (Task: {task_type})")

        req_msgs = messages if messages else [{"role": "user", "content": prompt}]
        payload = {
            "model": model,
            "messages": req_msgs,
            "stream": stream,
            "keep_alive": "10m",
            "options": {
                "temperature": params["temperature"],
                "num_predict": params["max_tokens"],
                "top_p": params["top_p"],
            }
        }
        if tools and not stream:
            payload["tools"] = tools

        # Timeout dinâmico baseado no tier do modelo
        _model_tier = (
            "heavy" if model == MODELS.get("heavy") else
            "fast"  if model in (MODELS.get("fast"), MODELS.get("basic")) else
            "main"
        )
        timeout = MODEL_TIMEOUTS.get(_model_tier, 120)

        for attempt in range(max_retries + 1):
            try:
                if self._session:
                    resp = self._session.post(OLLAMA_URL, json=payload, timeout=timeout, stream=stream)
                    resp.raise_for_status()
                    if stream:
                        def ollama_generator():
                            for line in resp.iter_lines():
                                if line:
                                    chunk = json.loads(line)
                                    if "message" in chunk and "content" in chunk["message"]:
                                        yield chunk["message"]["content"]
                        return ollama_generator()
                    else:
                        data = resp.json()
                        msg = data.get("message", {})
                        if msg.get("tool_calls"):
                            return {"tool_calls": _normalize_tool_calls(msg["tool_calls"]), "message": msg}
                        return msg.get("content", "").strip()
                else:
                    # Fallback para urllib se não houver requests
                    data_json = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(OLLAMA_URL, data=data_json, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        if stream:
                            def ollama_generator():
                                for line in resp:
                                    if line:
                                        chunk = json.loads(line)
                                        if "message" in chunk and "content" in chunk["message"]:
                                            yield chunk["message"]["content"]
                            return ollama_generator()
                        else:
                            data = json.loads(resp.read().decode())
                            msg = data.get("message", {})
                            if msg.get("tool_calls"):
                                return {"tool_calls": _normalize_tool_calls(msg["tool_calls"]), "message": msg}
                            return msg.get("content", "").strip()
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(1.5)
                else:
                    return "" if not stream else iter([f"[Erro Ollama: {e}]"])
        return ""

    def classify(self, text: str, categories: list[str]) -> str:
        cats = ", ".join(f'"{c}"' for c in categories)
        prompt = (
            f"Classifique o texto abaixo em UMA das categorias: {cats}\n"
            f"Responda APENAS com a categoria, sem explicações.\n\n"
            f"Texto: {text}\nCategoria:"
        )
        result = self.generate(prompt, task_type="command",
                                model=MODELS.get("fast", self.model))
        result = result.strip().strip('"').strip("'").lower()
        for cat in categories:
            if cat.lower() in result:
                return cat
        return categories[0]

    def is_ready(self) -> bool:
        return self.available


# Singleton
_llm_instance: Optional[LLMWrapper] = None

def get_llm() -> LLMWrapper:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMWrapper()
    return _llm_instance
