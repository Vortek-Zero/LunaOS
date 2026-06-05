#!/usr/bin/env python3
"""
actions/writer.py — Engine de escrita contextual da Luna
Adapta o estilo de linguagem ao contexto do pedido (adolescente, formal, thriller, etc.)
"""
from pathlib import Path
import re


# ── Planner — extrai estrutura + tom + personagem ───────────────────────────

PLANNER_PROMPT = """Você é o Arquiteto Narrativo da Luna.
Sua missão: analisar o pedido e devolver UMA ESTRUTURA ENXUTA em 4-6 bullet points.

EXTRAIA TAMBÉM:
- Tom detectado (adolescente, adulto, thriller, romance, infantil, neutro)
- Personagem principal (nome, idade, contexto social se mencionados)
- Ponto de vista (1ª pessoa, 3ª pessoa limitada, 3ª onisciente)

REGRAS:
- Não escreva o texto, apenas a estrutura
- Estrutura deve gerar narrativa, não ensaio
- Seja específico: "João perde o celular e fica sem contato com a única pessoa que importava" é melhor que "conflito"

Formato de resposta:
TOM: [detectado]
PERSONAGEM: [nome, idade, contexto]
POV: [ponto de vista]
ESTRUTURA:
- [cena/evento 1]
- [cena/evento 2]
...
"""

# ── Drafter — escrita adaptativa por contexto ───────────────────────────────

DRAFTER_SYSTEM_PROMPT = """Você é o Motor de Escrita da Luna — você escreve ficção realista.

════════════ REGRAS UNIVERSAIS (todo estilo) ════════════
1. PRIMEIRA LINHA obrigatória e exata: [FILE: nomedoarquivo.txt]
2. Show, don't tell — NUNCA "João sentia solidão". SEMPRE "João ficou olhando o teto às 2 da manhã sem ter com quem falar".
3. O narrador NÃO filosofa, NÃO moraliza, NÃO faz metáforas literárias por padrão.
4. Cada personagem tem voz, ritmo e vocabulário coerente com quem ele É.
5. ZERO formalidade acadêmica em contextos cotidianos.
6. ZERO: "era quase palpável", "profunda introspecção", "permeava a atmosfera", "silêncio eloquente".
7. Parágrafos curtos quando o personagem é agitado. Longos quando é calmo. Frases com ritmo.
8. Diálogos naturais — as pessoas cortam frases, usam "né", "cara", "tá", conforme o contexto.

════════════ REGRAS POR ESTILO ════════════

[ADOLESCENTE / JOVEM]
- Pensamentos concretos: "que horas são?", "o celular morreu", "minha mãe vai me matar"
- Não usa metáforas. Usa internet, jogos, redes sociais como referência real.
- Solidão = ficar sem resposta no WhatsApp. Não = contemplar o infinito.
- Fala pausada, às vezes brusca, às vezes travada.
- Interior: insegurança concreta, não poesia existencial.
ERRADO: "João perambulava pelos corredores da escola carregando o peso invisível da solidão"
CERTO:  "João comeu sozinho de novo. Colocou o fone antes mesmo de sentar."

[ADULTO / DRAMA]
- Consequências reais e tangíveis
- Passado aparece em detalhes específicos, não em flashbacks genéricos
- Vocabulário mais rico, mas não rebuscado

[THRILLER / SUSPENSE]
- Frases curtas em momentos de tensão
- O que NÃO é dito cria tensão
- Ação concreta antes de qualquer reflexão
- Nenhum personagem sabe mais do que deveria saber

[ROMANCE]
- Tensão antes do clímax emocional
- Detalhes sensoriais concretos (cheiro, textura, temperatura)
- Diálogo subtext — o que eles NÃO dizem importa mais

[INFANTIL]
- Linguagem simples, ritmo animado
- Emoções diretas e claras
- Aventura com consequências leves

════════════ INSTRUÇÃO FINAL ════════════
Detecte o tom a partir do plano fornecido e aplique as regras corretas.
A partir da segunda linha, escreva o texto direto. Sem introduções. Sem "Aqui está:".
"""

REFINER_PROMPT = """Você é a Revisora de Elite da Luna.
Sua missão: receber um rascunho e devolver a versão final limpa e humana.

RETORNE APENAS O TEXTO REVISADO. ZERO comentários, ZERO "Aqui está a versão revisada".

AÇÕES OBRIGATÓRIAS:
1. Elimine qualquer marca de IA: "Em primeiro lugar", "vale ressaltar", "é importante notar", "em suma", "em conclusão".
2. Verifique a VOZ do personagem — ela deve ser CONSISTENTE do início ao fim.
3. Se detectar adolescente: remova qualquer narrador filosófico que escapou. Deixe concreto.
4. Conecte os parágrafos com transições naturais, não com "Além disso" ou "Portanto".
5. Se o texto tiver mais de 3 parágrafos, verifique o ritmo — deve variar (curto, longo, curto).
6. Mantenha 100% da intenção narrativa original. Não adicione cenas novas.
7. Mantenha o tamanho aproximado do rascunho.
"""

# Palavras-chave que ativam o modo escritor
WRITER_TRIGGERS = [
    "escreva", "escreve", "escrever",
    "crie um texto", "cria um texto", "criar um texto",
    "crie uma historia", "crie um conto", "crie um poema",
    "crie um artigo", "crie uma redacao", "crie uma carta",
    "crie um roteiro", "crie uma cronica",
    "redija", "redige", "redigir",
    "componha", "compoe", "compor",
    "faca um texto", "faz um texto", "fazer um texto",
    "faca uma historia", "faca um conto", "faca um poema",
    "faca um artigo", "faca uma redacao",
    "texto dissertativo", "texto narrativo", "texto argumentativo",
    "texto descritivo", "texto expositivo",
    "luna writing", "modo escritora", "modo escritor",
    "salva um texto", "guarda um texto",
    "continue a historia", "continua a historia",
    "proxima cena", "próxima cena",
    "escreva o capitulo", "escreva o capítulo",
]


def _is_writing_verb(text_norm: str) -> bool:
    import re
    text_objects = r'(?:texto|historia|conto|poema|artigo|redacao|carta|roteiro|cronica|dissertacao|narrativa|ensaio|capitulo|paragrafo|introducao|conclusao|resumo|cena|dialogo|dialogo)'
    if re.search(r'(?:escreva|escreve|escrever|redija|redige|componha|compoe)\s+(?:um|uma)\s+' + text_objects, text_norm):
        return True
    if re.search(r'(?:escreva|escreve|escrever)\s+sobre\s+.{3,}', text_norm):
        return True
    if re.search(r'(?:quero|preciso|me\s+(?:faz|faca|da|de))\s+(?:um|uma)\s+' + text_objects, text_norm):
        return True
    if re.search(r'(?:continue|continua|continuar)\s+(?:a\s+)?(?:historia|conto|narrativa|texto)', text_norm):
        return True
    return False


class WriterManager:
    """Gerencia a criação de textos longos pela Luna."""

    def __init__(self):
        try:
            from config import WORKSPACE_DIR
            self.workspace = Path(WORKSPACE_DIR)
        except ImportError:
            self.workspace = Path("/home/pera/Luna-programming")
        self.workspace.mkdir(parents=True, exist_ok=True)

    def is_writing_request(self, text: str) -> bool:
        import unicodedata
        tl = text.lower()
        tl_norm = ''.join(c for c in unicodedata.normalize('NFD', tl) if unicodedata.category(c) != 'Mn')
        normalized_triggers = [
            ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
            for t in WRITER_TRIGGERS
        ]
        if any(trigger in tl_norm for trigger in normalized_triggers):
            return True
        return _is_writing_verb(tl_norm)

    def open_file_for_stream(self, filename: str):
        clean = Path(filename).name
        if not clean.endswith(".txt"):
            clean = clean.rsplit(".", 1)[0] + ".txt"
        filepath = self.workspace / clean
        return open(filepath, "w", encoding="utf-8"), filepath

    def build_planning_prompt(self, request: str) -> str:
        return f"{PLANNER_PROMPT}\n\nPedido do usuário:\n{request}"

    def build_draft_prompt(self, plan: str, request: str, context_text: str = "", characters: str = "", style: str = "") -> str:
        """Constrói o prompt de rascunho com contexto de personagem e estilo injetados."""
        extra = ""
        if characters:
            extra += f"\n\n[FICHA DOS PERSONAGENS]\n{characters}"
        if context_text:
            extra += f"\n\n[TEXTO JÁ ESCRITO — CONTINUE A PARTIR DAQUI]\n{context_text[-3000:]}"
        if style:
            extra += f"\n\n[ESTILO SOLICITADO]: {style}"
        return (
            f"{DRAFTER_SYSTEM_PROMPT}"
            f"{extra}"
            f"\n\n[ESTRUTURA E TOM DETECTADO]\n{plan}"
            f"\n\n[PEDIDO ORIGINAL]\n{request}"
        )

    def build_chapter_prompt(self, plan: str, request: str, context_text: str, chapter_num: int, characters: str = "") -> str:
        """Prompt para novo capítulo — injeta o contexto acumulado."""
        char_block = f"\n\n[FICHA DOS PERSONAGENS]\n{characters}" if characters else ""
        return (
            f"{DRAFTER_SYSTEM_PROMPT}"
            f"{char_block}"
            f"\n\n[CAPÍTULOS ANTERIORES — RESUMO/FINAL]\n{context_text[-4000:]}"
            f"\n\n[ESTRUTURA DO CAPÍTULO {chapter_num}]\n{plan}"
            f"\n\n[INSTRUÇÃO]\nEscreva o Capítulo {chapter_num}. Mantenha consistência de personagens, tom e estilo dos capítulos anteriores."
            f"\n\n[PEDIDO]\n{request}"
        )

    def build_refiner_prompt(self, draft: str) -> str:
        return f"{REFINER_PROMPT}\n\n[RASCUNHO]\n{draft}"

    def clean_chunk(self, chunk: str) -> str:
        """Limpeza de saída — remove markdown e padrões de IA."""
        chunk = re.sub(r'\*{1,3}', '', chunk)
        chunk = re.sub(r'#{1,6}\s*', '', chunk)
        chunk = re.sub(r'_{1,2}', '', chunk)
        chunk = re.sub(r'`{1,3}', '', chunk)
        # Padrões de IA a eliminar
        ai_patterns = [
            r'(?i)em primeiro lugar[,:\s]*',
            r'(?i)em segundo lugar[,:\s]*',
            r'(?i)em terceiro lugar[,:\s]*',
            r'(?i)argumento\s*\d+[,:\s]*',
            r'(?i)ponto\s*\d+[,:\s]*',
            r'(?i)em suma[,:\s]*',
            r'(?i)para concluir[,:\s]*',
            r'(?i)vale ressaltar(\sque)?[,:\s]*',
            r'(?i)é importante notar(\sque)?[,:\s]*',
            r'(?i)nesse sentido[,:\s]*',
            r'(?i)dessa forma[,:\s]*',
            r'(?i)portanto[,:\s]*',
            r'(?i)assim sendo[,:\s]*',
        ]
        for pat in ai_patterns:
            chunk = re.sub(pat, '', chunk)
        return chunk


# Singleton
_writer_instance = None

def get_writer() -> WriterManager:
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = WriterManager()
    return _writer_instance
