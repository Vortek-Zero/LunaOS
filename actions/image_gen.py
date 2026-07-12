"""Geração de imagens via Google Gemini.
Tenta modelos com suporte nativo a imagem: gemini-2.5-flash-image (grátis, rate-limited)
e Imagen 4.0 (requer plano pago).
"""
import uuid
from pathlib import Path
from config import GEMINI_API_KEY

PICTURES_DIR = Path.home() / "Pictures" / "Luna"

def generate_image(prompt: str, size: str = "1024x1024") -> str:
    if not GEMINI_API_KEY:
        return "FALHOU: GEMINI_API_KEY não configurada."

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "FALHOU: google-genai não instalado (pip install google-genai)."

    PICTURES_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Tenta modelos em ordem: flash-image (grátis) → Imagen 4.0 (pago)
    models_to_try = [
        ("gemini-2.5-flash-image", "generate_content"),
        ("gemini-2.0-flash-exp-image-generation", "generate_content"),
        ("imagen-4.0-generate-001", "imagen"),
    ]

    last_error = ""
    for model_name, mode in models_to_try:
        try:
            if mode == "generate_content":
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_modalities": ["Text", "Image"]},
                )
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                        image_data = part.inline_data.data
                        return _save_image(image_data, prompt)
                last_error = f"{model_name}: não retornou imagem"
            elif mode == "imagen":
                response = client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="1:1",
                    ),
                )
                if response.generated_images and response.generated_images[0].image:
                    image_data = response.generated_images[0].image.image_bytes
                    return _save_image(image_data, prompt)
                last_error = f"{model_name}: não retornou imagem"
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return "FALHOU: Cota diária de geração de imagens excedida (Gemini Free Tier). Tente novamente amanhã ou faça upgrade em https://ai.dev/projects."
            if "paid plans" in err_str or "payment" in err_str.lower():
                last_error = f"{model_name}: requer plano pago"
            else:
                last_error = f"{model_name}: {e}"
            continue

    return f"FALHOU: Nenhum modelo de geração de imagem disponível. {last_error}"


def _save_image(image_data: bytes, prompt: str) -> str:
    safe_name = "".join(c for c in prompt[:60] if c.isalnum() or c in " _-").strip() or "imagem"
    filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.png"
    filepath = PICTURES_DIR / filename
    try:
        filepath.write_bytes(image_data)
    except Exception as e:
        return f"FALHOU: Erro ao salvar imagem: {e}"
    return f"SUCESSO: Imagem gerada e salva em {filepath}"
