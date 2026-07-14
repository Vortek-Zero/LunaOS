#!/usr/bin/env python3
"""
brain/habit_learner.py — Analisador Automático de Hábitos da Luna
Analisa o log de atividades (activity_log.json) para descobrir padrões do usuário.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from collections import Counter
from typing import Dict, Any, List

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

ACTIVITY_LOG_FILE = Path(DATA_DIR) / "activity_log.json"

logger = logging.getLogger("luna.habit_learner")

class HabitLearner:
    """
    Analisa os logs de atividades recentes em busca de:
    - Padrões de horários (estuda à noite, trabalha de manhã, etc.)
    - Sequências de ações comuns (VS Code seguido de terminal)
    - Preferências de ferramentas e aplicativos recorrentes
    """
    def __init__(self):
        self.log_file = Path(ACTIVITY_LOG_FILE)

    def learn_habits(self) -> List[str]:
        """
        Executa a análise do histórico recente e retorna novos hábitos descobertos.
        """
        if not self.log_file.exists():
            return []

        try:
            log_data = json.loads(self.log_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Erro ao ler log de atividades para hábitos: {e}")
            return []

        if not log_data or len(log_data) < 20:
            # Precisa de uma base mínima de logs
            return []

        new_habits = []

        # 1. Análise de Horários de Uso Recorrentes
        hours = []
        for entry in log_data:
            try:
                dt = datetime.fromisoformat(entry.get("ts", ""))
                hours.append(dt.hour)
            except Exception:
                continue

        if hours:
            hour_counts = Counter(hours)
            # Verifica se há picos claros
            total_events = len(hours)
            
            # Padrão Noturno (22h às 05h)
            night_events = sum(count for h, count in hour_counts.items() if h >= 22 or h < 5)
            if night_events / total_events > 0.40:
                new_habits.append("Costuma trabalhar/programar no período noturno (após as 22h)")
            
            # Padrão Matinal (06h às 10h)
            morning_events = sum(count for h, count in hour_counts.items() if h >= 6 and h < 11)
            if morning_events / total_events > 0.35:
                new_habits.append("Costuma usar a assistente pela manhã (entre 06h e 10h)")

        # 2. Análise de Termos e Ferramentas Frequentes
        details_list = [e.get("details", "").lower() for e in log_data if e.get("action") == "user_input"]
        
        # Preferência por navegadores/sites
        firefox_count = sum(1 for d in details_list if "firefox" in d or "url" in d or "site" in d)
        if firefox_count > 5:
            new_habits.append("Usa com frequência o navegador Firefox para ler páginas ou acessar a web")
            
        # Programação / VS Code / Rust
        rust_count = sum(1 for d in details_list if "rust" in d or "cargo" in d)
        if rust_count > 4:
            new_habits.append("Está estudando ou programando em Rust recentemente")
            
        python_count = sum(1 for d in details_list if "python" in d or "pip" in d)
        if python_count > 5:
            new_habits.append("Utiliza muito Python no seu fluxo de trabalho")

        # Integrações de Casa Inteligente (Tuya / Luzes)
        light_count = sum(1 for d in details_list if "luz" in d or "apaga" in d or "acende" in d)
        if light_count > 3:
            new_habits.append("Interage com frequência para controlar lâmpadas/luzes inteligentes da casa")

        # 3. Consolida no perfil de usuário
        try:
            from brain.user_model import get_user_model
            user_model = get_user_model()
            
            # Evita duplicados
            existing_habits = user_model.profile.get("habits", [])
            added_any = False
            for habit in new_habits:
                if habit not in existing_habits:
                    user_model.update_from_llm("habits", habit)
                    added_any = True
                    logger.info(f"Hábito descoberto e consolidado: '{habit}'")
                    
            if added_any:
                # Dispara evento para o Event Bus
                try:
                    from brain.event_bus import get_event_bus
                    get_event_bus().publish("habit_discovered", new_habits)
                except ImportError:
                    pass
        except Exception as e:
            logger.error(f"Erro ao salvar hábitos no UserModel: {e}")

        return new_habits

# Helper para disparar a análise
def learn_user_habits():
    learner = HabitLearner()
    return learner.learn_habits()
