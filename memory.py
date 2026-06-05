#!/usr/bin/env python3
import json
import os
import difflib
import re
from datetime import datetime
from pathlib import Path

MEMORY_FILE = "memory.json"

class MemoryManager:
    def __init__(self, max_memories=50):
        self.memory_file = Path(MEMORY_FILE)
        self.max_memories = max_memories
        self.memories = self._load_memories()

    def _load_memories(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_memories(self):
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memories, f, indent=2, ensure_ascii=False)

    def add_memory(self, user_input, luna_output, resumo):
        """Adiciona uma memória com timestamp."""
        memoria = {
            "timestamp": datetime.now().isoformat(),
            "user": user_input,
            "luna": luna_output,
            "resumo": resumo
        }
        self.memories.append(memoria)
        # Limitar o número de memórias
        if len(self.memories) > self.max_memories:
            self.memories = self.memories[-self.max_memories:]
        self._save_memories()

    def get_recent_memories(self, limit=5):
        """Retorna as últimas 'limit' memórias."""
        return self.memories[-limit:]

    def search_memories(self, keyword):
        """Busca memórias que contenham a palavra-chave (simples)."""
        keyword = keyword.lower()
        results = []
        for m in self.memories:
            if keyword in m['user'].lower() or keyword in m['luna'].lower() or keyword in m['resumo'].lower():
                results.append(m)
        return results

    def extract_math_key(self, text):
        """Extracts math keywords for better similarity"""
        math_patterns = [
            r'[xyt]=\s*\d+',
            r'\d+\s*[\+\-\*\/]=\s*\d+',
            r'solve\s+for\s+[xyt]',
            r'calculate?\s+[xyt]',
        ]
        for pat in math_patterns:
            if re.search(pat, text.lower()):
                return 'math'
        return 'general'

    def get_relevant_memories(self, query: str, limit=3):
        """Fuzzy similarity + keyword search for relevant memories"""
        if not self.memories:
            return []

        query_lower = query.lower()
        math_key = self.extract_math_key(query)
        
        scored = []
        for mem in self.memories:
            mem_text = f"{mem['user']} {mem.get('luna', '')} {mem['resumo']}".lower()
            
            # Keyword boost
            keyword_score = 0
            query_words = query_lower.split()
            for word in query_words:
                if len(word) > 3 and word in mem_text:
                    keyword_score += 20
            
            # Fuzzy similarity
            fuzzy_ratio = difflib.SequenceMatcher(None, query_lower, mem_text).ratio()
            fuzzy_score = fuzzy_ratio * 100
            
            # Math boost
            mem_math = self.extract_math_key(f"{mem['user']} {mem.get('luna', '')}")
            if math_key == 'math' and mem_math == 'math':
                fuzzy_score += 30
            
            total_score = fuzzy_score + keyword_score
            if total_score > 30:  # Threshold
                scored.append((mem, total_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [mem for mem, score in scored[:limit]]

    def show_memories(self):
        if not self.memories:
            return "Nenhuma memória armazenada."
        output = "\n[MEMÓRIAS PERSISTENTES]\n" + "="*50 + "\n"
        for i, m in enumerate(reversed(self.memories[-10:]), 1):
            output += f"{i}. {m['timestamp'][:19]} - {m['resumo']}\n"
        return output

if __name__ == "__main__":
    mem = MemoryManager()
    # Teste rápido
    mem.add_memory("teste", "resposta", "teste de memória")
    print(mem.show_memories())