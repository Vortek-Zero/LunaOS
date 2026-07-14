#!/usr/bin/env python3
"""
brain/proactivity.py — Motor de Proatividade e Iniciativa da Luna
Gera avisos, sugestões e lembretes automáticos baseado em hábitos e horários do usuário.
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger("luna.proactivity")


class ProactivityEngine:
    """
    Motor de proatividade da Luna. Periodicamente avalia o contexto do usuário
    (horário, dia da semana, hábitos e metas) e propõe ações proativas.
    """

    def __init__(self, luna_core=None):
        self._luna = luna_core
        self._last_suggestion_time = 0

    def evaluate_proactive_actions(self) -> str | None:
        """
        Avalia se a Luna deve tomar iniciativa de sugerir algo baseado em hábitos.
        Retorna a mensagem de sugestão proativa se elegível, None caso contrário.
        """
        now = datetime.now()
        current_timestamp = time.time()

        # Só sugere no máximo a cada 2 horas para não ser irritante
        if current_timestamp - self._last_suggestion_time < 7200:
            return None

        try:
            from brain.user_model import get_user_model

            user_model = get_user_model()
            habits = user_model.profile.get("habits", [])

            suggestion = None

            # 1. Hábito noturno de programação
            if now.hour >= 21 or now.hour < 1:
                has_night_coding = any("período noturno" in h or "programar" in h for h in habits)
                if has_night_coding:
                    suggestion = "Olá! Percebi que você costuma programar a esta hora da noite. Gostaria que eu abrisse o VS Code e preparasse seu workspace?"

            # 2. Hábito matutino de leitura/notícias
            elif 6 <= now.hour < 10:
                has_morning_use = any("pela manhã" in h for h in habits)
                if has_morning_use:
                    suggestion = "Bom dia! Pronto para começar? Gostaria que eu fizesse seu briefing matinal e mostrasse sua agenda de hoje?"

            # 3. Lembrar de objetivos de longa data se ocioso
            if not suggestion and habits:
                # Sugere revisar objetivos se for fim de semana
                if now.weekday() in [5, 6] and 14 <= now.hour <= 17:
                    suggestion = "Final de semana é um ótimo momento para revisar seus objetivos! Gostaria de checar seu progresso no plano 'Evoluir Luna' ou 'Aprender Rust'?"

            if suggestion:
                self._last_suggestion_time = current_timestamp
                # Envia notificação desktop
                self._trigger_desktop_notification(suggestion)
                # Publica no Event Bus
                try:
                    from brain.event_bus import get_event_bus

                    get_event_bus().publish("proactive_suggestion", suggestion)
                except ImportError:
                    pass
                return suggestion

        except Exception as e:
            logger.error(f"Erro ao avaliar ações proativas: {e}")

        return None

    def _trigger_desktop_notification(self, message: str):
        """Envia notificação via notify-send se disponível."""
        try:
            import subprocess

            subprocess.run(["notify-send", "Luna 🌙", message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Notificação proativa enviada: '{message}'")
        except Exception:
            pass

    def speak_suggestion(self, suggestion: str):
        """Falar a sugestão se a Luna estiver com voz ativa."""
        if not self._luna:
            return
        try:
            from voice.tts import get_tts

            get_tts().speak(suggestion, blocking=False)
        except Exception:
            pass
