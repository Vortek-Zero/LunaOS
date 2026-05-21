#!/usr/bin/env python3
"""
brain/llm.py — LLM híbrido: Gemini (primário) → Groq (fallback) → Ollama (local)

Prioridade:
  1. Gemini 2.5 Flash  → main/heavy/fast  (online, rápido, 1M contexto)
  2. Groq              → llama-3.1-8b     (fallback quando Gemini indisponível)
  3. Ollama            → qwen2.5 local    (fallback offline)

Fallback ativado em:
  - Rate limit Gemini (429)
  - Gemini offline / sem key
  - Erro de conexão
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
        OLLAMA_GENERATE_URL as OLLAMA_URL,
        OLLAMA_TAGS_URL,
        MODELS,
        MODEL_TIMEOUTS,
        GROQ_API_KEY,
        GROQ_MODELS,
        GEMINI_API_KEY,
        GEMINI_MODELS,
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
        "heavy": "llama-3.3-70b-versatile",
        "main":  "llama-3.1-8b-instant",
        "fast":  "llama-3.1-8b-instant",
    }
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODELS = {
        "heavy": "gemini-2.5-flash-preview-05-20",
        "main":  "gemini-2.5-flash-preview-05-20",
        "fast":  "gemini-2.5-flash-preview-05-20",
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
                result.append(NormalizedToolCall(
                    id=tc.get("id", f"call_{len(result)}"),
                    type=tc.get("type", "function"),
                    function=ToolCallFunction(
                        name=fn.get("name", ""),
                        arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                    ),
                ))
            else:
                fn = tc.function
                result.append(NormalizedToolCall(
                    id=getattr(tc, "id", f"call_{len(result)}"),
                    type=getattr(tc, "type", "function"),
                    function=ToolCallFunction(name=fn.name, arguments=fn.arguments),
                ))
        except Exception as e:
            print(f"[LLM] ⚠ Erro ao normalizar tool_call: {e}")
    return result


TASK_PARAMS = {
    "factual":        {"temperature": 0.05, "top_p": 0.85, "max_tokens": 500},
    "creative":       {"temperature": 0.85, "top_p": 0.95, "max_tokens": 3000},
    "command":        {"temperature": 0.1,  "top_p": 0.90, "max_tokens": 200},
    "planning":       {"temperature": 0.15, "top_p": 0.90, "max_tokens": 500},
    "coding":         {"temperature": 0.1,  "top_p": 0.90, "max_tokens": 4000},
    "conversational": {"temperature": 0.70, "top_p": 0.95, "max_tokens": 1500},
    "default":        {"temperature": 0.2,  "top_p": 0.90, "max_tokens": 500},
}


def _ollama_model_for_tier(model_name: str) -> str:
    """Dado um modelo Gemini/Groq, retorna o equivalente Ollama."""
    gemini_vals = set(GEMINI_MODELS.values()) if GEMINI_MODELS else set()
    groq_vals = set(GROQ_MODELS.values()) if GROQ_MODELS else set()
    if model_name in gemini_vals or model_name in groq_vals:
        return MODELS["main"]
    return model_name


class LLMWrapper:
    """
    Interface unificada: Gemini 2.5 Flash → Groq → Ollama.
    Fallback automático e transparente para o resto do sistema.
    """

    def __init__(self, model: str = None):
        self.model = model or MODELS["main"]
        self.available = False
        self._stop_flag = False

        # ── Gemini ────────────────────────────────────────────
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
                print(f"[LLM] ⚠ Gemini não inicializou: {e}")
                self._gemini_ok = False

        # ── Groq (fallback 1) ─────────────────────────────────
        self._groq_ok = HAS_GROQ_LIB and bool(GROQ_API_KEY)
        self._groq_rl_until = 0.0
        self._groq = None
        if self._groq_ok:
            try:
                self._groq = GroqClient(api_key=GROQ_API_KEY)
                print("[LLM] ✓ Groq API ativo (fallback 1)")
                if not self.available:
                    self.available = True
            except Exception as e:
                print(f"[LLM] ⚠ Groq não inicializou: {e}")
                self._groq_ok = False

        # ── Ollama (fallback 2 — local) ───────────────────────
        if HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        else:
            self._session = None

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

    def _gemini_available(self) -> bool:
        if not self._gemini_ok:
            return False
        if time.time() < self._gemini_rl_until:
            return False
        # Verifica se há pelo menos um modelo sem rate limit
        now = time.time()
        models = [GEMINI_MODELS.get(k) for k in ("main", "fallback", "fallback2") if GEMINI_MODELS.get(k)]
        return any(now >= self._gemini_rl_per_model.get(m, 0) for m in models)

    def _groq_available(self) -> bool:
        return self._groq_ok and time.time() >= self._groq_rl_until

    def _gemini_model_for(self, model_hint: str) -> str:
        """Retorna o modelo Gemini disponível, pulando os que estão em rate limit."""
        now = time.time()
        ordered = [
            GEMINI_MODELS.get("main",      "gemini-2.5-flash"),
            GEMINI_MODELS.get("fallback",  "gemini-2.0-flash"),
            GEMINI_MODELS.get("fallback2", "gemini-2.5-flash-lite"),
        ]
        for m in ordered:
            if now >= self._gemini_rl_per_model.get(m, 0):
                return m
        # Todos em rate limit — retorna o último (vai cair no Groq depois)
        return ordered[-1]

    def _groq_model_for(self, model_hint: str) -> str:
        groq_vals = set(GROQ_MODELS.values())
        if model_hint in groq_vals:
            return model_hint
        if model_hint == MODELS.get("heavy"):
            return GROQ_MODELS["heavy"]
        if model_hint in (MODELS.get("fast"), MODELS.get("basic")):
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
        tools: list = None,
    ) -> Union[str, Generator, dict]:

        if tools:
            stream = False

        used_model = model or self.model

        # 1. Gemini (primário)
        if self._gemini_available():
            gemini_model = self._gemini_model_for(used_model)
            result = self._generate_gemini(prompt, task_type, gemini_model, stream, messages, tools)
            if result is not None:
                return result

        # 2. Groq (fallback 1)
        if self._groq_available():
            groq_model = self._groq_model_for(used_model)
            result = self._generate_groq(prompt, task_type, groq_model, stream, messages, tools)
            if result is not None:
                return result

        # 3. Ollama (fallback local)
        ollama_model = _ollama_model_for_tier(used_model)
        if self._ollama_ok or self._check_ollama():
            self._ollama_ok = True
            return self._generate_ollama(prompt, task_type, ollama_model, stream, max_retries, messages, tools)

        return "" if not stream else iter(["[LLM indisponível]"])

    # ── Gemini ────────────────────────────────────────────────

    def _generate_gemini(
        self, prompt: str, task_type: str, model: str, stream: bool,
        messages: list = None, tools: list = None
    ) -> Optional[Union[str, Generator, dict]]:
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
            for msg in messages[:-1]:  # tudo menos a última mensagem
                role = msg.get("role", "user")
                content = msg.get("content") or ""
                if role == "system":
                    system_instruction = content
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})
                elif role == "user":
                    history.append({"role": "user", "parts": [content]})
                elif role == "tool":
                    # Resultado de ferramenta — injeta como mensagem do modelo
                    history.append({"role": "model", "parts": [f"[Resultado da ferramenta]: {content}"]})
            # Última mensagem é o input atual
            last = messages[-1]
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
                    tool_calls.append(NormalizedToolCall(
                        id=f"gemini_{fc.name}_{int(time.time())}",
                        type="function",
                        function=ToolCallFunction(
                            name=fc.name,
                            arguments=json.dumps(args_dict),
                        ),
                    ))

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
                    # Todos os modelos Gemini em rate limit — cai no Groq
                    self._gemini_rl_until = time.time() + 60
                    print(f"[LLM] ⚠ Todos os modelos Gemini em quota — fallback Groq por 60s")
                else:
                    print(f"[LLM] ⚠ Gemini {model} quota — tentando {next_model}")
                    return self._generate_gemini(prompt, task_type, next_model, stream, messages, tools)
            elif "400" in err or "api_key" in err.lower() or "invalid" in err.lower():
                print(f"[LLM] ⚠ Gemini key inválida — desativando")
                self._gemini_ok = False
            else:
                print(f"[LLM] ⚠ Gemini erro: {e} — tentando Groq")
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
            declarations.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": clean_params,
            })
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
                print("[LLM] ⚠ Gemini rate limit no stream — fallback Groq")
            else:
                print(f"[LLM] ⚠ Gemini stream erro: {e} — fallback Groq")

        # Fallback para Groq no stream
        if self._groq_available():
            groq_model = self._groq_model_for(model)
            params = TASK_PARAMS.get(task_type, TASK_PARAMS["default"])
            msgs = history + [{"role": "user", "content": user_content}]
            # Converte formato Gemini → OpenAI
            oai_msgs = [{"role": "user" if m["role"] == "user" else "assistant", "content": m["parts"][0] if isinstance(m.get("parts"), list) else m.get("content", "")} for m in msgs]
            yield from self._groq_stream(oai_msgs, groq_model, params, prompt=user_content, task_type=task_type)
            return

        # Fallback para Ollama no stream
        ollama_model = _ollama_model_for_tier(model)
        yield from self._generate_ollama(
            prompt=user_content, task_type=task_type, model=ollama_model,
            stream=True, max_retries=1,
        )

    # ── Groq ──────────────────────────────────────────────────

    def _generate_groq(
        self, prompt: str, task_type: str, model: str, stream: bool,
        messages: list = None, tools: list = None
    ) -> Optional[Union[str, Generator, dict]]:
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
                self._groq_rl_until = time.time() + 60
                print(f"[LLM] ⚠ Groq rate limit — fallback Ollama por 60s")
            elif "401" in err or "authentication" in err.lower():
                print(f"[LLM] ⚠ Groq key inválida — desativando")
                self._groq_ok = False
            else:
                print(f"[LLM] ⚠ Groq erro: {e} — tentando Ollama")
            return None

    def _groq_stream(self, messages: list, model: str, params: dict, prompt: str = None, task_type: str = "default") -> Generator:
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
                print("[LLM] ⚠ Groq rate limit no stream — fallback Ollama")
            else:
                print(f"[LLM] ⚠ Groq stream erro: {e} — fallback Ollama")

        ollama_model = _ollama_model_for_tier(model)
        yield from self._generate_ollama(
            prompt=prompt, task_type=task_type, model=ollama_model,
            stream=True, max_retries=1, messages=messages,
        )

    # ── Ollama ────────────────────────────────────────────────

    def _generate_ollama(
        self, prompt: str, task_type: str, model: str, stream: bool,
        max_retries: int = 2, messages: list = None, tools: list = None
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

        _model_tier = (
            "heavy" if model == MODELS.get("heavy") else
            "fast"  if model in (MODELS.get("fast"), MODELS.get("basic")) else
            "main"
        )
        timeout = MODEL_TIMEOUTS.get(_model_tier, 120)
        ollama_chat_url = OLLAMA_URL.replace("/api/generate", "/api/chat")

        for attempt in range(max_retries + 1):
            try:
                if self._session:
                    resp = self._session.post(ollama_chat_url, json=payload, timeout=timeout, stream=stream)
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
                    data_json = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(ollama_chat_url, data=data_json, headers={"Content-Type": "application/json"})
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
        result = self.generate(prompt, task_type="command", model=MODELS.get("fast", self.model))
        result = result.strip().strip('"').strip("'").lower()
        for cat in categories:
            if cat.lower() in result:
                return cat
        return categories[0]

    def is_ready(self) -> bool:
        return self.available

    # Expõe _use_groq para compatibilidade com luna_core.py
    def _use_groq(self, task_type: str = "default") -> bool:
        return self._groq_available()


# Singleton
_llm_instance: Optional[LLMWrapper] = None

def get_llm() -> LLMWrapper:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMWrapper()
    return _llm_instance
