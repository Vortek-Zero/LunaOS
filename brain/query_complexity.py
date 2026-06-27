"""
brain/query_complexity.py — Classificação de complexidade de consultas (inspirado no OpenJarvis)
Roteia consultas para o modelo/task_type adequado baseado em análise de intenção.
"""
import re
from typing import Optional

# Padrões de intenção
_CODE_PATTERNS = re.compile(
    r"(c[oó]digo|programa[rç]|desenvolve|script|funç[ãa]o|classe|"
    r"api|html?|css|javascript|python|jsx|tsx|refatora|debuga|"
    r"teste unit[áa]rio|implementa|comita|commit|git push|frontend|backend|"
    r"fullstack|banco de dados|sql|modelagem|algoritmo|estrutura de dados|"
    r"complexidade|performan[cç]e|otimiza)", re.IGNORECASE
)

_ARCH_PATTERNS = re.compile(
    r"(arquitetura|design pattern|padr[ãa]o de projeto|microservi[cç]o|"
    r"infraestrutura|docker|kubernetes|aws|deploy|ci/cd|pipeline|"
    r"refatora[çc][ãa]o profunda|m[oó]dulo|componentiza[çc][ãa]o)", re.IGNORECASE
)

_PROJECT_PATTERNS = re.compile(
    r"(cria\s+(um|o)\s+(projeto|site|app|aplicativo|sistema|"
    r"calculadora|jogo|bot|dashboard|backend|frontend))|"
    r"(projeto\s+(para|de|em)\s+\w+)", re.IGNORECASE
)

_FILE_PATTERNS = re.compile(
    r"(cria\s+(um|o)\s+arquivo|escreve|salva\s+em|"
    r"arquivo\s+chamado|com\s+o\s+nome)", re.IGNORECASE
)

_COMPLEX_ANALYSIS = re.compile(
    r"(analisa\s+profundamente|compara[çc][ãa]o detalhada|"
    r"pesquisa\s+completa|relat[óo]rio\s+detalhado|"
    r"resumo\s+extens[oa]|traduz\s+documento|"
    r"revis[aã]o\s+completa)", re.IGNORECASE
)

_MULTI_STEP = re.compile(
    r"(primeiro.*depois|passo\s+1|etapa|em\s+sequ[eê]ncia|"
    r"e\s+ent[aã]o\s+|\be\b.*\be\b.*lista)", re.IGNORECASE
)

_SIMPLE_GREETING = re.compile(
    r"^(oi|ol[áa]|bom\s+dia|boa\s+tarde|boa\s+noite|"
    r"e a[ií]|fala[ai]?\s*[aã]?\s*|hey|luna[,.!]?\s*$)", re.IGNORECASE
)

_WEB_SEARCH = re.compile(
    r"(pesquisa|busca|procura\s+na\s+web|"
    r"o\s+que\s+[ée]\s+|quem\s+[ée]\s+|"
    r"not[íi]cia|cota[çc][ãa]o|clima|pre[çc]o)", re.IGNORECASE
)


class ComplexityLevel:
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    CODE = "code"


def classify_query(query: str) -> dict:
    """
    Classifica a complexidade de uma consulta e retorna metadados de execução.
    """
    if not query or not query.strip():
        return _default()

    tl = query.strip().lower()

    # 1. Arquitetura ou Projeto Complexo → heavy + planning/coding
    if _ARCH_PATTERNS.search(tl) or _PROJECT_PATTERNS.search(tl):
        return {
            "complexity": ComplexityLevel.CODE,
            "model_tier": "heavy",
            "task_type": "coding" if _CODE_PATTERNS.search(tl) else "planning",
            "needs_tools": True,
            "is_code_request": True,
            "is_project_request": True,
            "is_web_search": False,
        }

    # 2. Código/desenvolvimento → decide entre main e heavy
    if _CODE_PATTERNS.search(tl) or _FILE_PATTERNS.search(tl):
        # Queries técnicas curtas podem usar main, mas qualquer coisa com substância vai para heavy
        heavy_keywords = [
            "implementa", "refatora", "debug", "testes", "corrige", "analisa",
            "cria um", "desenvolve", "como funciona", "explica", "melhora",
            "otimiza", "ajusta", "conecta", "integra"
        ]
        is_heavy = len(query) > 40 or any(kw in tl for kw in heavy_keywords)
        return {
            "complexity": ComplexityLevel.CODE if is_heavy else ComplexityLevel.MEDIUM,
            "model_tier": "heavy" if is_heavy else "main",
            "task_type": "coding",
            "needs_tools": True,
            "is_code_request": True,
            "is_project_request": bool(_FILE_PATTERNS.search(tl)),
            "is_web_search": False,
        }

    # 3. Saudações simples → simple + fast
    if _SIMPLE_GREETING.match(tl):
        return {
            "complexity": ComplexityLevel.SIMPLE,
            "model_tier": "fast",
            "task_type": "conversational",
            "needs_tools": False,
            "is_code_request": False,
            "is_project_request": False,
            "is_web_search": False,
        }

    # 4. Pesquisa web → medium + factual
    if _WEB_SEARCH.search(tl):
        return {
            "complexity": ComplexityLevel.MEDIUM,
            "model_tier": "main",
            "task_type": "factual",
            "needs_tools": True,
            "is_code_request": False,
            "is_project_request": False,
            "is_web_search": True,
        }

    # 5. Análise complexa / multi-step → heavy + planning
    if _COMPLEX_ANALYSIS.search(tl) or _MULTI_STEP.search(tl) or len(query) > 200:
        return {
            "complexity": ComplexityLevel.COMPLEX,
            "model_tier": "heavy",
            "task_type": "planning",
            "needs_tools": True,
            "is_code_request": False,
            "is_project_request": False,
            "is_web_search": False,
        }

    # 6. Comandos/ferramentas → medium + command
    local_keywords = [
        "abre", "abrir", "toca", "fecha", "mata", "processo",
        "volume", "luz", "timer", "lembrete", "print", "screenshot",
        "clica", "digita", "envia", "manda",
    ]
    if any(kw in tl for kw in local_keywords):
        return {
            "complexity": ComplexityLevel.MEDIUM,
            "model_tier": "main",
            "task_type": "command",
            "needs_tools": True,
            "is_code_request": False,
            "is_project_request": False,
            "is_web_search": False,
        }

    # 7. Conversa normal → medium + conversational
    return {
        "complexity": ComplexityLevel.MEDIUM,
        "model_tier": "main",
        "task_type": "conversational",
        "needs_tools": False,
        "is_code_request": False,
        "is_project_request": False,
        "is_web_search": False,
    }


def _default() -> dict:
    return {
        "complexity": ComplexityLevel.MEDIUM,
        "model_tier": "main",
        "task_type": "conversational",
        "needs_tools": False,
        "is_code_request": False,
        "is_project_request": False,
        "is_web_search": False,
    }
