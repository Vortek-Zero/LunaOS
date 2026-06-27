"""Geração de imagens via Google Gemini Imagen (grátis com API key)."""
import os
import uuid
from pathlib import Path
from config import GEMINI_API_KEY

PICTURES_DIR = Path.home() / "Pictures" / "Luna"

def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Gera uma imagem via Google Gemini (Imagen).
    Usa o modelo gemini-2.0-flash-exp-image-generation que suporta
    saída nativa de imagens (gratuito com a API key do Gemini).
    Retorna caminho do arquivo salvo ou mensagem de erro.
    """
    if not GEMINI_API_KEY:
        return "FALHOU: GEMINI_API_KEY não configurada."

    try:
        from google import genai
    except ImportError:
        return "FALHOU: google-genai não instalado (pip install google-genai)."

    PICTURES_DIR.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=GEMINI_API_KEY)

    model = "gemini-2.0-flash-exp-image-generation"

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_modalities": ["Text", "Image"],
            },
        )
    except Exception as e:
        return f"FALHOU: API Gemini retornou erro: {e}"

    image_data = None
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
            image_data = part.inline_data.data
            break

    if not image_data:
        return f"FALHOU: Gemini não gerou imagem. Resposta: {response.text[:200] if hasattr(response, 'text') else 'vazia'}"

    safe_name = "".join(c for c in prompt[:60] if c.isalnum() or c in " _-").strip() or "imagem"
    filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.png"
    filepath = PICTURES_DIR / filename

    try:
        filepath.write_bytes(image_data)
    except Exception as e:
        return f"FALHOU: Erro ao salvar imagem: {e}"

    return f"SUCESSO: Imagem gerada e salva em {filepath}"
