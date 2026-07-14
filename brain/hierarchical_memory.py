#!/usr/bin/env python3
"""
brain/hierarchical_memory.py — Coordenador de Memória Hierárquica da Luna
Organiza as memórias em camadas (Curta, Episódica, Semântica, Perfil e Objetivos) para evitar poluição do contexto.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("luna.hierarchical_memory")


class HierarchicalMemory:
    """
    Coordenador central que unifica o acesso a todas as camadas de memória da assistente.
    Evita redundâncias e garante que apenas informações relevantes sejam injetadas no contexto do prompt.
    """

    def __init__(self, core_memory=None):
        self.core_memory = core_memory  # Referência ao brain.memory.Memory (sqlite) de curta/média duração

    def get_unified_context(self, query: str) -> str:
        """
        Retorna o contexto unificado e filtrado a ser fornecido ao prompt do LLM.
        Busca em todas as camadas de forma balanceada.
        """
        parts = []

        # 1. Camada de Histórico de Conversa Curta (SQLite)
        if self.core_memory:
            try:
                mem_ctx = self.core_memory.get_context_for_prompt(query)
                if mem_ctx:
                    # Corta se for muito grande
                    if len(mem_ctx) > 2500:
                        mem_ctx = mem_ctx[:2500] + "\n[... histórico de conversa truncado]"
                    parts.append(mem_ctx)
            except Exception as e:
                logger.error(f"Erro ao recuperar memória curta: {e}")

        # 2. Camada de Perfil Dinâmico (Preferences / Skills)
        try:
            from brain.user_model import get_user_model

            user_model_ctx = get_user_model().get_context()
            if user_model_ctx:
                parts.append(user_model_ctx)
        except Exception as e:
            logger.error(f"Erro ao recuperar modelo do usuário: {e}")

        # 3. Camada de Objetivos Permanentes
        try:
            goals_file = Path(__file__).parent.parent / "config" / "goals.json"
            if goals_file.exists():
                goals_data = json.loads(goals_file.read_text(encoding="utf-8"))
                active_goals = [g for g in goals_data if g.get("status") != "concluido"]
                if active_goals:
                    goals_lines = ["[OBJETIVOS ATIVOS DO USUÁRIO]"]
                    for g in active_goals:
                        goals_lines.append(f"• {g.get('title')} (Prioridade: {g.get('priority')})")
                    parts.append("\n".join(goals_lines))
        except Exception as e:
            logger.error(f"Erro ao recuperar objetivos permanentes: {e}")

        # 4. Camada de Memória Episódica (Experiências Recentes)
        try:
            from brain.episodic_memory import get_episodic_memory

            # Pega o resumo geral de episódios recentes + episódios específicos relacionados à query
            episodic_mem = get_episodic_memory()
            general_episodes = episodic_mem.get_recent_summary(n_days=7)
            specific_episodes = episodic_mem.recall(query, days=30, limit=3)

            episodic_parts = []
            if general_episodes:
                episodic_parts.append(general_episodes)
            if specific_episodes:
                formatted_specific = episodic_mem.format_for_user(specific_episodes)
                episodic_parts.append(f"[EPISÓDIOS ESPECÍFICOS RELEVANTES]\n{formatted_specific}")

            if episodic_parts:
                parts.append("\n\n".join(episodic_parts))
        except Exception as e:
            logger.error(f"Erro ao recuperar memórias episódicas: {e}")

        # 5. Camada de Memória Semântica Profunda (RAG ChromaDB)
        try:
            from brain.memory_rag import MemoryRAG

            rag = MemoryRAG()
            if rag.enabled:
                semantic_ctx = rag.retrieve_context(query, n_results=3)
                if semantic_ctx:
                    parts.append(semantic_ctx)
        except Exception as e:
            logger.error(f"Erro ao recuperar memória semântica: {e}")

        return "\n\n".join(parts)

    def consolidate_episodic_to_semantic(self, days_ago: int = 14):
        """
        Consolida episódios antigos/experiências na memória semântica vetorial (ChromaDB)
        para liberar espaço nos logs do dia a dia e manter a base histórica compacta.
        """
        try:
            from datetime import datetime, timedelta

            from brain.episodic_memory import get_episodic_memory
            from brain.memory_rag import MemoryRAG

            episodic_mem = get_episodic_memory()
            rag = MemoryRAG()
            if not rag.enabled:
                return

            cutoff = datetime.now() - timedelta(days=days_ago)
            to_consolidate = []

            with episodic_mem._lock:
                remaining_episodes = []
                for ep in episodic_mem._episodes:
                    try:
                        ep_dt = datetime.fromisoformat(ep["ts"])
                        if ep_dt < cutoff:
                            to_consolidate.append(ep)
                        else:
                            remaining_episodes.append(ep)
                    except Exception:
                        remaining_episodes.append(ep)

                # Substitui os logs na memória episódica ativa
                episodic_mem._episodes = remaining_episodes
                episodic_mem._save()

            if to_consolidate:
                for ep in to_consolidate:
                    text_to_save = f"Em {ep.get('date')}, o usuário pediu: '{ep.get('text')}' e o resultado foi: '{ep.get('summary')}'"
                    rag.remember(text_to_save, source="consolidated_episode")
                logger.info(f"Consolidadas {len(to_consolidate)} memórias episódicas antigas para a memória semântica.")
        except Exception as e:
            logger.error(f"Erro ao consolidar memória episódica para semântica: {e}")
