"""
voice/voice_engine.py — Engine de voz inteligente (Yara)
Análise de emoção, normalização, siglas, matemática, segmentação e cache.
"""
import re
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Tipos de segmento ─────────────────────────────────────────
SEGMENT_SPEECH = "speech"
SEGMENT_SIGLA  = "sigla"
SEGMENT_MATH   = "math"
SEGMENT_PAUSE  = "pause"

# ── Mapeamento de símbolos matemáticos (só em contexto explícito) ────
MATH_MAP = {
    r'\+': ' mais ',
    r'\-': ' menos ',
    r'\*': ' vezes ',
    r'\/': ' dividido por ',
    r'=':  ' igual a ',
    r'>':  ' maior que ',
    r'<':  ' menor que ',
}

# Contexto matemático explícito: expressões com números e operadores
_MATH_CONTEXT_RE = re.compile(r'\d[\s]*[+\-*/=><][\s]*\d|\d+%|\d+\s*(?:mais|menos|vezes|dividido)')

# Bullets/listas → frase natural
_BULLET_RE = re.compile(r'^\s*[-•*▸►▶·]\s+', re.MULTILINE)
_NUMBERED_RE = re.compile(r'^\s*\d+[.)]\s+', re.MULTILINE)

# Emojis e símbolos não faláveis
_EMOJI_RE = re.compile(
    r'[\U00010000-\U0010ffff'
    r'\u2600-\u26FF\u2700-\u27BF'
    r'\u2300-\u23FF\u25A0-\u25FF'
    r'\u2190-\u21FF\u2000-\u206F'
    r'✓✗✔✘→←↑↓▸►▶◆●○□■]',
    flags=re.UNICODE
)

# ── Palavras-chave por emoção ─────────────────────────────────
EMOTION_KEYWORDS = {
    "excited": [
        "pronto", "concluído", "arquivo criado", "timer", "alarme disparado",
        "lembrete criado", "adicionado", "salvo", "feito", "listo",
    ],
    "happy": [
        "ótimo", "incrível", "parabéns", "feliz", "adorei", "perfeito",
        "maravilhoso", "excelente", "que bom", "boa notícia", "consegui",
        "funcionou", "sucesso", "amei", "adorável", "fantástico", "top",
        "show", "demais", "sensacional", "uhuul", "yay", "eba",
    ],
    "sad": [
        "triste", "infelizmente", "lamento", "sinto muito", "pena",
        "difícil", "não consegui", "falhou", "perdeu", "morreu",
        "acabou", "desculpe", "desculpa", "foi embora", "saudade",
        "chateado", "decepcionado", "que pena",
    ],
    "angry": [
        "erro", "falha", "problema", "impossível", "absurdo",
        "não funciona", "travou", "bugou", "que raiva", "irritante",
        "ridículo", "inaceitável", "péssimo", "horrível", "odeio",
    ],
    "surprised": [
        "uau", "nossa", "sério", "inacreditável", "surpreendente",
        "caramba", "meu deus", "não acredito", "impressionante",
        "que coisa", "como assim", "de verdade", "sério mesmo",
    ],
    "calm": [
        "ok", "certo", "entendido", "claro", "com certeza", "tranquilo",
        "sem problema", "pode deixar", "tudo bem", "combinado",
    ],
}

# ── Parâmetros de voz por emoção ──────────────────────────────
EMOTION_PARAMS = {
    "neutral":   {"rate": "+5%",   "pitch": "+2Hz",  "jitter": 2},
    "happy":     {"rate": "+22%",  "pitch": "+5Hz",  "jitter": 3},
    "sad":       {"rate": "-15%",  "pitch": "-4Hz",  "jitter": 1},
    "angry":     {"rate": "+12%",  "pitch": "+3Hz",  "jitter": 2},
    "surprised": {"rate": "+10%",  "pitch": "+7Hz",  "jitter": 4},
    "calm":      {"rate": "-8%",   "pitch": "-2Hz",  "jitter": 1},
    "excited":   {"rate": "+28%",  "pitch": "+8Hz",  "jitter": 5},
}


@dataclass
class Segment:
    text: str
    kind: str  # speech | sigla | math | pause
    emotion: str = "neutral"


@dataclass
class VoiceParams:
    rate: str
    pitch: str
    volume: str = "+5%"


class VoiceEngine:
    """
    Processa texto bruto → lista de segmentos prontos para TTS,
    com parâmetros de voz ajustados por emoção.
    """

    def __init__(self):
        self._cache: dict[str, tuple[list[Segment], VoiceParams]] = {}

    # ── API pública ───────────────────────────────────────────

    def process(self, text: str, base_volume: str = "+5%") -> tuple[list[Segment], VoiceParams]:
        """
        Retorna (segmentos, params_de_voz).
        Usa cache por hash(texto).
        """
        key = hashlib.md5(text.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]

        text = self._normalize(text)
        emotion = self._detect_emotion(text)
        segments = self._segment(text, emotion)
        params = self._build_params(emotion, base_volume)

        self._cache[key] = (segments, params)
        return segments, params

    def segments_to_text(self, segments: list[Segment]) -> str:
        """Junta segmentos em texto falável final."""
        parts = []
        for seg in segments:
            if seg.kind == SEGMENT_PAUSE:
                parts.append(",")
            else:
                parts.append(seg.text)
        return " ".join(p for p in parts if p.strip())

    # ── Normalização ──────────────────────────────────────────

    def _normalize(self, text: str) -> str:
        # Remove markdown bold/italic/code
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'`[^`]*`', '', text)
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        # Remove URLs completamente (não falar "https dois pontos barra barra...")
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)
        # Remove emojis e símbolos não faláveis
        text = _EMOJI_RE.sub('', text)
        # Remove prefixos de sistema que vazam na voz
        text = re.sub(r'\[(?:Router|LLM|Cache|Perf|Writer|Timer|Parser|Executor|Vision|Coder)\][^\n]*\n?', '', text)
        # Converte listas/bullets em frases naturais (vírgula entre itens)
        # "• item1\n• item2" → "item1, item2"
        lines = text.split('\n')
        prose_lines = []
        bullet_items = []
        for line in lines:
            stripped = _BULLET_RE.sub('', line).strip()
            stripped = _NUMBERED_RE.sub('', stripped).strip()
            if _BULLET_RE.search(line) or _NUMBERED_RE.search(line):
                if stripped:
                    bullet_items.append(stripped)
            else:
                if bullet_items:
                    prose_lines.append(', '.join(bullet_items) + '.')
                    bullet_items = []
                if stripped:
                    prose_lines.append(stripped)
        if bullet_items:
            prose_lines.append(', '.join(bullet_items) + '.')
        text = ' '.join(prose_lines)
        # Remove headers markdown
        text = re.sub(r'#{1,6}\s*', '', text)
        # Remove underscores de ênfase
        text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
        # Trunka respostas muito longas para TTS (máx 600 chars)
        if len(text) > 600:
            cut = text[:600]
            last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
            text = cut[:last_dot + 1] if last_dot > 100 else cut
        # Fix hífens entre palavras → espaço
        text = re.sub(r'(?<=[a-záàâãéèêíïóôõúüçA-ZÁÀÂÃÉÈÊÍÏÓÔÕÚÜÇ])-(?=[a-záàâãéèêíïóôõúüçA-ZÁÀÂÃÉÈÊÍÏÓÔÕÚÜÇ])', ' ', text)
        # Normaliza pontuação repetida e espaços
        text = re.sub(r'([.!?]){2,}', r'\1', text)
        text = re.sub(r',{2,}', ',', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    # ── Detecção de emoção ────────────────────────────────────

    def _detect_emotion(self, text: str) -> str:
        lower = text.lower()
        scores = {e: 0 for e in EMOTION_KEYWORDS}
        for emotion, words in EMOTION_KEYWORDS.items():
            for w in words:
                if w in lower:
                    # Frases exatas valem mais que palavras soltas
                    scores[emotion] += 2 if " " in w else 1
        # Pontuação como sinal de emoção
        if "!" in text:
            scores["happy"] += 1
            scores["surprised"] += 1
        if "?" in text:
            scores["surprised"] += 1
        if text.isupper() and len(text) > 5:
            scores["angry"] += 2
        best = max(scores, key=lambda e: scores[e])
        return best if scores[best] > 0 else "neutral"

    # ── Segmentação ───────────────────────────────────────────

    def _segment(self, text: str, emotion: str) -> list[Segment]:
        """
        Divide o texto em segmentos.
        Matemática só é traduzida quando há contexto numérico explícito
        (ex: '2 + 3', '50%', '10 / 2') — nunca em texto corrido.
        """
        segments: list[Segment] = []
        clauses = re.split(r'(?<=[.!?;])\s+|(?<=,)\s+', text)
        is_math_context = bool(_MATH_CONTEXT_RE.search(text))

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            tokens = clause.split()
            current_speech: list[str] = []

            for token in tokens:
                # Sigla: 2-6 letras maiúsculas
                if re.fullmatch(r'[A-Z]{2,6}', token):
                    if current_speech:
                        segments.append(Segment(" ".join(current_speech), SEGMENT_SPEECH, emotion))
                        current_speech = []
                    segments.append(Segment(" ".join(list(token)), SEGMENT_SIGLA, emotion))

                # Operadores matemáticos: só traduz se há contexto numérico
                elif is_math_context and re.search(r'[\+\-\*/=><]', token):
                    if current_speech:
                        segments.append(Segment(" ".join(current_speech), SEGMENT_SPEECH, emotion))
                        current_speech = []
                    segments.append(Segment(self._translate_math(token), SEGMENT_MATH, emotion))

                else:
                    current_speech.append(token)

            if current_speech:
                segments.append(Segment(" ".join(current_speech), SEGMENT_SPEECH, emotion))

        return segments if segments else [Segment(text, SEGMENT_SPEECH, emotion)]

    # ── Tradução matemática ───────────────────────────────────

    def _translate_math(self, text: str) -> str:
        for pattern, replacement in MATH_MAP.items():
            text = re.sub(pattern, replacement, text)
        return re.sub(r'\s+', ' ', text).strip()

    # ── Parâmetros de voz ─────────────────────────────────────

    def _build_params(self, emotion: str, volume: str) -> VoiceParams:
        p = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
        rate_val = int(re.search(r'[+-]?\d+', p["rate"]).group())
        jitter = random.randint(-p["jitter"], p["jitter"])
        rate_val = max(-50, min(50, rate_val + jitter))
        rate = f"{rate_val:+d}%"
        return VoiceParams(rate=rate, pitch=p["pitch"], volume=volume)

    # ── Pós-processamento de áudio (numpy/scipy) ──────────────

    @staticmethod
    def postprocess_audio(data, samplerate: int):
        """
        Aplica EQ leve e normalização de loudness.
        Requer numpy + scipy. Retorna (data, samplerate) processados.
        """
        try:
            import numpy as np
            from scipy import signal as sp_signal

            # Garante float32
            data = data.astype(np.float32)

            # 9.2 EQ: corta graves abaixo de 80 Hz (high-pass)
            sos_hp = sp_signal.butter(4, 80.0, btype='high', fs=samplerate, output='sos')
            data = sp_signal.sosfilt(sos_hp, data, axis=0)

            # Leve boost de presença 8-12 kHz (peak filter)
            nyq = samplerate / 2.0
            if nyq > 10000:
                f0 = 10000.0
                Q = 1.5
                gain_db = 2.0
                A = 10 ** (gain_db / 40.0)
                w0 = f0 / nyq
                alpha = np.sin(w0 * np.pi) / (2 * Q)
                b = [1 + alpha * A, -2 * np.cos(w0 * np.pi), 1 - alpha * A]
                a = [1 + alpha / A, -2 * np.cos(w0 * np.pi), 1 - alpha / A]
                data = sp_signal.lfilter(b, a, data, axis=0)

            # 9.4 Normalização final: alvo -14 LUFS (mais alto e claro para caixas)
            rms = np.sqrt(np.mean(data ** 2))
            if rms > 0:
                target_rms = 10 ** (-14 / 20.0)
                data = data * (target_rms / rms)

            # Humanização: variação de timing ±10-30ms
            shift_samples = int(random.uniform(0.01, 0.03) * samplerate)
            if shift_samples > 0:
                data = np.roll(data, shift_samples, axis=0)

            # Clamp para evitar clipping
            data = np.clip(data, -1.0, 1.0)

        except ImportError:
            pass  # sem numpy/scipy, retorna sem processar

        return data, samplerate


# Singleton
_engine: Optional[VoiceEngine] = None


def get_voice_engine() -> VoiceEngine:
    global _engine
    if _engine is None:
        _engine = VoiceEngine()
    return _engine
