#!/usr/bin/env python3
"""
test_puter_models.py — Testa todos os modelos disponíveis via Puter.
Uso: uv run python tests/test_puter_models.py
"""

import asyncio
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

try:
    from config import PUTER_TOKEN
except ImportError:
    PUTER_TOKEN = ""

import aiohttp

PUTER_URL = "https://api.puter.com/drivers/call"

MODELS = [
    ("gpt-5.5", "🥇 Cérebro principal"),
    ("gpt-5.2", "🥈 Programação"),
    ("o3", "🥉 Raciocínio"),
    ("claude-sonnet-5", "📝 Escrita"),
    ("gpt-5-mini", "⚡ Velocidade"),
    ("grok-3", "🎨 Criatividade"),
    ("deepseek-r1-0528", "🔍 Segunda opinião"),
    ("gpt-4.1", "🔧 Compatibilidade"),
    ("gpt-4o", "🔧 Compatibilidade"),
    ("llama-4-maverick", "🦙 Meta Maverick"),
    ("llama-4-scout", "🦙 Meta Scout"),
]

HEADERS = {
    "Authorization": f"Bearer {PUTER_TOKEN}",
    "Content-Type": "application/json",
}


async def _run_model_test(session, model: str, label: str) -> dict:
    payload = {
        "interface": "puter-chat-completion",
        "provider": "openai-completion",
        "method": "complete",
        "args": {
            "messages": [{"role": "user", "content": "Say 'OK'"}],
            "model": model,
            "stream": False,
            "max_tokens": 50,
        },
    }
    # Modelos de raciocínio (o3, gpt-5-mini, etc) podem precisar de max_tokens maior
    if model in ("o3", "gpt-5-mini"):
        payload["args"]["max_tokens"] = 200
    start = time.time()
    try:
        async with session.post(
            PUTER_URL, json=payload, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            elapsed = time.time() - start
            if resp.status == 200:
                data = await resp.json()
                msg = data.get("result", {}).get("message", {})
                raw_content = msg.get("content") or ""
                if isinstance(raw_content, list):
                    # Claude Anthropic format: [{"type":"text","text":"OK"}]
                    texts = [b.get("text", "") for b in raw_content if isinstance(b, dict) and b.get("type") == "text"]
                    content = " ".join(texts).strip()
                else:
                    content = str(raw_content).strip()
                cost = data.get("result", {}).get("usage", {}).get("usd_cents", 0)
                # Alguns modelos retornam conteúdo vazio (finish_reason=length)
                # mas ainda assim estão funcionais — considerar sucesso se não houve erro
                finish = data.get("result", {}).get("finish_reason", "")
                is_ok = bool(content) or finish == "length"
                return {
                    "model": model,
                    "label": label,
                    "status": "✓" if is_ok else "⚠",
                    "content": content or f"(finish={finish})",
                    "elapsed": round(elapsed, 2),
                    "cost_cents": cost,
                    "error": None,
                }
            else:
                body = await resp.text()
                return {
                    "model": model,
                    "label": label,
                    "status": "✗",
                    "content": "",
                    "elapsed": round(elapsed, 2),
                    "cost_cents": 0,
                    "error": f"HTTP {resp.status}: {body[:120]}",
                }
    except TimeoutError:
        return {
            "model": model,
            "label": label,
            "status": "✗",
            "content": "",
            "elapsed": round(time.time() - start, 2),
            "cost_cents": 0,
            "error": "Timeout (30s)",
        }
    except Exception as e:
        return {
            "model": model,
            "label": label,
            "status": "✗",
            "content": "",
            "elapsed": round(time.time() - start, 2),
            "cost_cents": 0,
            "error": str(e),
        }


async def main():
    print("=" * 60)
    print("  🧪 Teste de Modelos Puter — Luna AI")
    print("=" * 60)
    print()

    if not PUTER_TOKEN:
        print("  ❌ PUTER_TOKEN não configurado no .env")
        sys.exit(1)

    async with aiohttp.ClientSession() as session:
        results = []
        for model_name, label in MODELS:
            results.append(await _run_model_test(session, model_name, label))
            await asyncio.sleep(0.5)  # evitar rate limit

    print(f"  {'Modelo':<22} {'Status':<6} {'Tempo':<8} {'Custo':<10} Resposta")
    print("  " + "-" * 60)
    total_cost = 0
    passed = 0
    failed = 0

    for r in results:
        status_icon = r["status"]
        cost_str = f"${r['cost_cents'] * 0.01:.4f}" if r["cost_cents"] > 0 else "-"
        content_preview = (r["content"][:30] + "..") if r["content"] else ""
        error_preview = (r["error"][:40] + "..") if r["error"] else ""
        print(
            f"  {r['label']:<4} {r['model']:<16} {status_icon:<6} {r['elapsed']:<8.1f}s {cost_str:<10} {content_preview or error_preview}"
        )
        total_cost += r["cost_cents"]
        if r["status"] == "✓":
            passed += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print(f"  ✅ {passed}/{len(results)} modelos OK    ❌ {failed} falhas")
    print(f"  💰 Custo total do teste: ${total_cost * 0.01:.4f}")
    print(f"  ⏱  Tempo total: {sum(r['elapsed'] for r in results):.1f}s")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
