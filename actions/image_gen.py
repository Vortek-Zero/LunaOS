"""Geração de imagens via Puter (dev tier, gratuito) + Google Gemini."""

import json
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from config import GEMINI_API_KEY, PUTER_BASE_URL, PUTER_TOKEN

PICTURES_DIR = Path.home() / "Pictures" / "Luna"

PUTER_IMAGE_MODEL = "dall-e-3"


def generate_image(prompt: str, size: str = "1024x1024") -> str:
    PICTURES_DIR.mkdir(parents=True, exist_ok=True)
    import config

    for provider in config.IMAGE_CASCADE_ORDER:
        provider = provider.strip().lower()
        if provider == "puter" and PUTER_TOKEN:
            result = _try_puter(prompt, size)
            if result:
                return result
        elif provider == "gemini" and GEMINI_API_KEY:
            result = _try_gemini(prompt)
            if result:
                return result

    configured = []
    if PUTER_TOKEN:
        configured.append("Puter")
    if GEMINI_API_KEY:
        configured.append("Gemini")

    if not configured:
        return "FALHOU: Nenhuma chave de API configurada. Defina PUTER_TOKEN ou GEMINI_API_KEY no .env."
    return f"FALHOU: Os provedores testados ({', '.join(configured)}) falharam ou estão sem cota. Verifique a cota ou alterne o cascade."


def _try_puter(prompt: str, size: str) -> str | None:
    try:
        payload = json.dumps(
            {
                "interface": "puter-image",
                "method": "generate",
                "args": {
                    "prompt": prompt,
                    "model": PUTER_IMAGE_MODEL,
                    "size": size,
                    "n": 1,
                },
            }
        ).encode()
        req = Request(
            f"{PUTER_BASE_URL}/drivers/call",
            data=payload,
            headers={
                "Authorization": f"Bearer {PUTER_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("result", {})
            image_url = result.get("url") or result.get("data", [{}])[0].get("url", "")
            if image_url:
                from urllib.request import urlopen as dl

                image_data = dl(image_url, timeout=60).read()
                return _save_image(image_data, prompt)
            alt = result.get("alt") or result.get("data", [{}])[0].get("b64_json", "")
            if alt:
                import base64

                image_data = base64.b64decode(alt)
                return _save_image(image_data, prompt)
        return None
    except Exception as e:
        print(f"[ImageGen] Puter falhou: {e}")
        return None


def _try_gemini(prompt: str) -> str | None:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)
    models_to_try = [
        ("gemini-2.5-flash-image", "generate_content"),
        ("gemini-2.0-flash-exp-image-generation", "generate_content"),
        ("imagen-4.0-generate-001", "imagen"),
    ]

    for model_name, mode in models_to_try:
        try:
            if mode == "generate_content":
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_modalities": ["Text", "Image"]},
                )
                for part in response.candidates[0].content.parts:
                    if (
                        part.inline_data
                        and part.inline_data.mime_type
                        and part.inline_data.mime_type.startswith("image/")
                    ):
                        return _save_image(part.inline_data.data, prompt)
            elif mode == "imagen":
                response = client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
                )
                if response.generated_images and response.generated_images[0].image:
                    return _save_image(response.generated_images[0].image.image_bytes, prompt)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return None  # Let Puter take over
            if "paid plans" in err_str or "payment" in err_str.lower():
                continue
            print(f"[ImageGen] Gemini {model_name} falhou: {e}")
            continue
    return None


def _save_image(image_data: bytes, prompt: str) -> str:
    safe_name = "".join(c for c in prompt[:60] if c.isalnum() or c in " _-").strip() or "imagem"
    filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.png"
    filepath = PICTURES_DIR / filename
    try:
        filepath.write_bytes(image_data)
    except Exception as e:
        return f"FALHOU: Erro ao salvar imagem: {e}"
    return f"SUCESSO: Imagem gerada e salva em {filepath}"
