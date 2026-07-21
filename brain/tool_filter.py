#!/usr/bin/env python3
"""
brain/tool_filter.py — Filtro Inteligente de Contexto de Ferramentas.
Seleciona e ordena apenas as 4-8 ferramentas mais relevantes para cada prompt,
reduzindo o envio de 57 ferramentas para o LLM por requisição.
"""

import re
from typing import Any


# Categorias de ferramentas para classificação de intenção
TOOL_CATEGORIES = {
    "filesystem": [
        "read_text",
        "write_text",
        "edit_file",
        "list_directory",
        "create_directory",
        "delete_file",
        "move_file",
        "copy_file",
        "search_files",
    ],
    "browser": [
        "open_url",
        "search_web",
        "click_web_result",
        "web_navigate",
        "web_screenshot",
    ],
    "system": [
        "run_bash_command",
        "run_terminal_command",
        "open_app",
        "close_app",
        "kill_process",
        "system_control",
        "control_window",
    ],
    "voice": ["tts_speak", "stt_listen", "play_audio", "stop_audio"],
    "media": ["play_music", "pause_music", "next_track", "set_volume", "get_volume"],
    "image": ["image_generate", "image_describe", "screenshot", "ocr_image"],
    "app_control": ["open_app", "close_app", "switch_window", "minimize_window", "maximize_window"],
    "communication": ["whatsapp_action", "send_email", "send_message"],
    "creative": ["write_text", "image_generate", "create_project"],
    "utility": ["timer", "alarm", "reminder", "calendar_event", "clipboard"],
}

# Mapeamento de palavras-chave para categorias
KEYWORD_TO_CATEGORY = {
    "arquivo": "filesystem",
    "arquivos": "filesystem",
    "pasta": "filesystem",
    "diretório": "filesystem",
    "ler": "filesystem",
    "escrever": "filesystem",
    "editar": "filesystem",
    "criar arquivo": "filesystem",
    "navegador": "browser",
    "browser": "browser",
    "chrome": "browser",
    "firefox": "browser",
    "pesquisar": "browser",
    "buscar": "browser",
    "google": "browser",
    "site": "browser",
    "url": "browser",
    "link": "browser",
    "terminal": "system",
    "bash": "system",
    "comando": "system",
    "executar": "system",
    "rodar": "system",
    "instalar": "system",
    "processo": "system",
    "falar": "voice",
    "audio": "voice",
    "voz": "voice",
    "escutar": "voice",
    "música": "media",
    "musica": "media",
    "spotify": "media",
    "volume": "media",
    "imagem": "image",
    "foto": "image",
    "print": "image",
    "captura": "image",
    "tela": "image",
    "abrir": "app_control",
    "fechar": "app_control",
    "aplicativo": "app_control",
    "programa": "app_control",
    "whatsapp": "communication",
    "mensagem": "communication",
    "email": "communication",
    "enviar": "communication",
    "escrever": "creative",
    "gerar": "creative",
    "criar": "creative",
    "texto": "creative",
    "história": "creative",
    "alarme": "utility",
    "lembrete": "utility",
    "timer": "utility",
    "cronômetro": "utility",
    "clipboard": "utility",
    "copiar": "utility",
    "colar": "utility",
}


def _classify_intent(text: str) -> list[str]:
    """Classifica o prompt em categorias de ferramentas relevantes.
    
    Returns:
        Lista de categorias ordenadas por relevância (primeira = mais relevante)
    """
    text_lower = text.lower()
    scores: dict[str, int] = {}

    # Conta ocorrências de keywords por categoria
    for keyword, category in KEYWORD_TO_CATEGORY.items():
        if keyword in text_lower:
            scores[category] = scores.get(category, 0) + 1

    # Ordena categorias por score (decrescente)
    sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Retorna apenas nomes de categorias, removendo duplicatas
    seen = set()
    result = []
    for cat, _ in sorted_categories:
        if cat not in seen:
            seen.add(cat)
            result.append(cat)

    # Se nenhuma categoria foi detectada, retorna categorias genéricas
    if not result:
        result = ["utility", "system"]

    return result


def _get_tools_by_category(category: str, all_tools: list[dict]) -> list[dict]:
    """Filtra ferramentas de uma categoria específica."""
    tool_names = TOOL_CATEGORIES.get(category, [])
    filtered = []
    for tool in all_tools:
        fn = tool.get("function", {})
        name = fn.get("name", "")
        if name in tool_names:
            filtered.append(tool)
    return filtered


def _score_tool(tool: dict, text: str) -> float:
    """Atribui score de relevância a uma ferramentabaseado no texto do prompt.
    
    Quanto mais vezes o nome da ferramenta ou suas palavras-chave aparecerem no texto,
    maior o score.
    """
    text_lower = text.lower()
    fn = tool.get("function", {})
    name = fn.get("name", "")
    description = fn.get("description", "")

    score = 0.0

    # Match exato no nome da ferramenta
    if name and name in text_lower:
        score += 10.0

    # Match parcial no nome
    if name:
        # Verifica se palavras do nome da ferramenta aparecem no texto
        name_parts = name.replace("_", " ").split()
        for part in name_parts:
            if part in text_lower:
                score += 3.0

    # Match na descrição
    if description:
        desc_words = description.lower().split()
        for word in desc_words:
            if word in text_lower and len(word) > 3:
                score += 0.5

    # Pequeno fator aleatório para desempate (estabilidade)
    import hashlib
    hash_val = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    score += (hash_val % 100) / 1000.0

    return score


def filter_tools_for_query(text: str, all_tools: list[dict], max_tools: int = 8) -> list[dict]:
    """Filtra e ordena ferramentas relevantes para um prompt específico.
    
    Args:
        text: Texto do prompt/pergunta do usuário
        all_tools: Lista completa de ferramentas disponíveis
        max_tools: Número máximo de ferramentas a retornar (padrão: 8)
    
    Returns:
        Lista de ferramentas filtradas e ordenadas por relevância
    """
    if not all_tools:
        return []

    # Se o número total de ferramentas for pequeno, retorna todas
    if len(all_tools) <= max_tools:
        return all_tools

    # Classifica intenção do prompt
    categories = _classify_intent(text)

    # Coleta ferramentas das categorias relevantes (até 3 categorias)
    candidate_tools = []
    seen_ids = set()

    for category in categories[:3]:
        cat_tools = _get_tools_by_category(category, all_tools)
        for tool in cat_tools:
            tool_id = tool.get("function", {}).get("name", "")
            if tool_id not in seen_ids:
                seen_ids.add(tool_id)
                candidate_tools.append(tool)

    # Se não encontrou ferramentas específicas, usa todas como candidatas
    if not candidate_tools:
        candidate_tools = all_tools

    # Pontua cada ferramenta candidata
    scored_tools = []
    for tool in candidate_tools:
        score = _score_tool(tool, text)
        scored_tools.append((score, tool))

    # Ordena por score (decrescente)
    scored_tools.sort(key=lambda x: x[0], reverse=True)

    # Retorna as N melhores ferramentas
    result = [tool for _, tool in scored_tools[:max_tools]]

    return result


def get_tool_filter_stats(original_count: int, filtered_count: int) -> dict:
    """Retorna estatísticas do filtro de ferramentas para logging."""
    return {
        "original_tools": original_count,
        "filtered_tools": filtered_count,
        "reduction_ratio": filtered_count / original_count if original_count > 0 else 0,
        "reduction_percent": (1 - filtered_count / original_count) * 100 if original_count > 0 else 0,
    }