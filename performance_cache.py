#!/usr/bin/env python3
"""
Cache Inteligente e Otimizações de Performance para LUNA
Reduz latência de resposta e uso de CPU/GPU
"""

import json
import hashlib
import heapq
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from pathlib import Path
import time
import threading


class SmartCache:
    """
    Cache inteligente com expiração temporal e heurísticas de relevância.
    Otimizado para IA com respostas frequentes.
    """

    def __init__(self, cache_file: str = None, ttl_hours: int = 24):
        """
        Inicializa cache inteligente com L1 em memória + L2 em disco.

        Args:
            cache_file: Arquivo JSON onde armazenar cache (L2)
            ttl_hours: Tempo de vida em horas para cada entrada
        """
        if cache_file is None:
            try:
                from config import CACHE_FILE
                cache_file = str(CACHE_FILE)
            except ImportError:
                cache_file = str(Path(__file__).parent / "data" / "cache.json")

        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600
        self.cache = self._load_cache()
        self._l1_cache: Dict[str, Dict] = {}  # Cache em memória (L1 — latência zero)
        self._dirty = False  # Flag para saber se precisa salvar
        self._lock = threading.Lock()
        self._flush_timer = None
        self._start_flush_timer()
        self.hit_count = {}  # Rastreamento de hits para estatísticas
        self.miss_count = {}

        # Popula L1 com entradas existentes do disco
        for key, entry in self.cache.get("entries", {}).items():
            self._l1_cache[key] = entry

    def _load_cache(self) -> Dict:
        """Carrega cache do arquivo; repara JSON corrompido automaticamente."""
        empty = {"entries": {}, "metadata": {"created": datetime.now().isoformat()}}
        if not self.cache_file.exists():
            return empty
        try:
            raw = self.cache_file.read_text(encoding="utf-8").strip()
            if not raw:
                return empty
            return json.loads(raw)
        except Exception as e:
            print(f"[CACHE WARN] Erro ao carregar cache: {e} — resetando.")
            try:
                backup = self.cache_file.with_suffix(".json.bak")
                self.cache_file.rename(backup)
                print(f"[CACHE] Backup salvo em {backup}")
            except Exception:
                pass
            return empty

    def clear_all(self) -> int:
        """Remove todas as entradas do cache (L1 + L2)."""
        with self._lock:
            count = len(self.cache.get("entries", {}))
            self.cache = {"entries": {}, "metadata": {"created": datetime.now().isoformat()}}
            self._l1_cache.clear()
            self.hit_count.clear()
            self.miss_count.clear()
            self._dirty = False
            self._save_cache()
            return count

    def _save_cache(self) -> None:
        """Persiste cache em arquivo"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[CACHE WARN] Erro ao salvar cache: {e}")

    def _start_flush_timer(self) -> None:
        """Flush dirty cache to disk every 30 seconds."""
        if self._flush_timer is not None:
            self._flush_timer.cancel()
        self._flush_timer = threading.Timer(30.0, self._periodic_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _periodic_flush(self) -> None:
        try:
            self.flush()
        finally:
            self._start_flush_timer()

    def _hash_query(self, query: str) -> str:
        """Cria hash SHA256 da query para chave de cache"""
        return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]

    def get(self, query: str) -> Optional[Dict]:
        """
        Recupera resposta em cache se disponível e válida.
        Usa L1 (memória) primeiro, depois L2 (disco).
        Retorna None se não encontrado ou expirado.
        Thread-safe.
        """
        query_hash = self._hash_query(query)

        with self._lock:
            # L1 — busca em memória (latência zero)
            entry = self._l1_cache.get(query_hash)

            # L2 — fallback para disco
            if entry is None:
                entry = self.cache.get("entries", {}).get(query_hash)

            if entry is None:
                self.miss_count[query_hash] = self.miss_count.get(query_hash, 0) + 1
                return None

            # Verifica expiração
            created_at = datetime.fromisoformat(entry.get("timestamp", datetime.now().isoformat()))
            if datetime.now() - created_at > timedelta(seconds=self.ttl_seconds):
                self._l1_cache.pop(query_hash, None)
                self.cache.get("entries", {}).pop(query_hash, None)
                self._dirty = True
                self.miss_count[query_hash] = self.miss_count.get(query_hash, 0) + 1
                return None

            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["last_accessed"] = datetime.now().isoformat()
            # Sync back to L2 cache for persistence
            self.cache["entries"][query_hash] = entry
            self._dirty = True
            self.hit_count[query_hash] = self.hit_count.get(query_hash, 0) + 1

            return {
                "response": entry.get("response"),
                "confidence": entry.get("confidence", 0.8),
                "source": "cache",
            }

    def set(self, query: str, response: str, confidence: float = 0.8, ttl_hours: Optional[int] = None) -> None:
        """
        Armazena resposta em cache.

        Args:
            query: Pergunta/entrada do usuário
            response: Resposta gerada
            confidence: Nível de confiança (0-1)
            ttl_hours: Tempo de vida customizado
        """
        query_hash = self._hash_query(query)

        # Calcula expiração
        ttl = (ttl_hours or 24) * 3600
        expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat()

        entry = {
            "query": query,  # Armazena query original para debug
            "response": response,
            "confidence": min(confidence, 1.0),  # Normaliza 0-1
            "timestamp": datetime.now().isoformat(),
            "expires_at": expires_at,
            "access_count": 1,
            "last_accessed": datetime.now().isoformat(),
        }

        with self._lock:
            if "entries" not in self.cache:
                self.cache["entries"] = {}

            self.cache["entries"][query_hash] = entry
            self._l1_cache[query_hash] = entry
            self._dirty = True

            # Eviction LRU quando excede limite
            try:
                from config import CACHE_MAX_ENTRIES
                max_entries = CACHE_MAX_ENTRIES
            except ImportError:
                max_entries = 500

            entries = self.cache["entries"]
            if len(entries) > max_entries:
                # Use heapq for O(log N) LRU eviction
                heap = [
                    (entry.get("last_accessed", ""), key)
                    for key, entry in entries.items()
                ]
                heapq.heapify(heap)
                to_remove = len(entries) - max_entries
                for _ in range(to_remove):
                    if heap:
                        _, old_key = heapq.heappop(heap)
                        entries.pop(old_key, None)
                        self._l1_cache.pop(old_key, None)

            self._dirty = True

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                self._save_cache()
                self._dirty = False

    def clear_expired(self) -> int:
        with self._lock:
            removed = 0
            if "entries" not in self.cache:
                return removed
            expired_keys = []
            for key, entry in self.cache["entries"].items():
                try:
                    expires_at = datetime.fromisoformat(entry.get("expires_at", datetime.now().isoformat()))
                    if datetime.now() > expires_at:
                        expired_keys.append(key)
                        removed += 1
                except Exception:
                    pass
            for key in expired_keys:
                del self.cache["entries"][key]
                self._l1_cache.pop(key, None)  # P3: also remove from L1
            if removed > 0:
                self._save_cache()
            return removed

    def get_stats(self) -> Dict:
        """Retorna estatísticas de uso do cache"""
        return {
            "total_entries": len(self.cache.get("entries", {})),
            "hits": sum(self.hit_count.values()),
            "misses": sum(self.miss_count.values()),
            "hit_rate": self._calculate_hit_rate(),
            "cache_file": str(self.cache_file),
        }

    def _calculate_hit_rate(self) -> float:
        """Calcula taxa de acerto do cache"""
        total_hits = sum(self.hit_count.values())
        total_misses = sum(self.miss_count.values())
        total = total_hits + total_misses

        return (total_hits / total * 100) if total > 0 else 0.0


class ResponseOptimizer:
    """
    Otimizador de respostas para reduzir tempo de processamento.
    Implementa heurísticas inteligentes de seleção de modelo e parâmetros.
    """

    def __init__(self):
        """Inicializa otimizador"""
        self.model_performance = {}  # Rastreamento de performance por modelo

    def optimize_temperature(self, is_question: bool, confidence: float = 0.5) -> float:
        """
        Define temperatura otimizada baseada na intenção.

        Menor temperatura = respostas mais determinísticas (bom para fatos)
        Maior temperatura = respostas mais criativas (bom para chat)
        """
        if is_question:
            # Pergunta: precisa precisão, mas não tão severo
            if confidence > 0.8:
                return 0.05  # Muito factual
            elif confidence > 0.5:
                return 0.15  # Moderadamente factual
            else:
                return 0.3   # Um pouco mais criativo se incerto
        else:
            # Chat/comando: pode ser mais criativo
            return 0.4

    def optimize_top_p(self, response_length_estimate: int = 50) -> float:
        """
        Define top_p (nucleus sampling) baseado no comprimento esperado.

        Respostas curtas: top_p menor (mais determinístico)
        Respostas longas: top_p maior (mais diversidade)
        """
        if response_length_estimate < 20:
            return 0.8  # Resposta muito curta
        elif response_length_estimate < 100:
            return 0.85
        elif response_length_estimate < 500:
            return 0.9
        else:
            return 0.95  # Resposta longa, precisa coerência

    def optimize_max_tokens(self, is_question: bool, context_length: int = 0) -> int:
        """
        Define max_tokens otimizado.

        Pergunta curta → resposta curta
        Pergunta longa com contexto → resposta média-longa
        """
        if is_question:
            return min(256 + (context_length // 10), 1024)
        else:
            return 128

    def should_use_fast_model(self, query_length: int, has_context: bool = False) -> bool:
        """
        Heurística para decidir se deve usar modelo mais rápido (1B) vs completo (3B).

        Queries simples/curtas → modelo rápido
        Queries complexas → modelo completo
        """
        if query_length < 20 and not has_context:
            return True  # Query muito curta, modelo rápido é suficiente
        return False

    def estimate_response_time(self, query_length: int, model_size: str = "3b") -> float:
        """
        Estima tempo de resposta em segundos (heurística).
        Útil para UI feedback.
        """
        base_time = {
            "1b": 0.5,      # Modelo pequeno: ~0.5s
            "3b": 1.0,      # Modelo médio: ~1s
            "7b": 2.5,      # Modelo grande: ~2.5s
            "13b": 4.0,     # Modelo muito grande: ~4s
        }

        model_time = base_time.get(model_size, 1.0)
        length_factor = 1.0 + (query_length / 100) * 0.2  # Cada 100 chars = +20% tempo

        return model_time * length_factor

    def get_optimization_hints(self, query: str, is_question: bool, confidence: float) -> Dict:
        """
        Retorna dicas completas de otimização para processamento.
        Use isso como referência para o main.py.
        """
        query_len = len(query)
        is_simple = query_len < 30

        return {
            "use_fast_model": self.should_use_fast_model(query_len),
            "temperature": self.optimize_temperature(is_question, confidence),
            "top_p": self.optimize_top_p(),
            "max_tokens": self.optimize_max_tokens(is_question),
            "is_simple_query": is_simple,
            "estimated_time": self.estimate_response_time(query_len, "3b"),
        }


class PerformanceMonitor:
    """
    Monitor de performance para rastreamento em tempo real.
    Ajuda a identificar gargalos.
    """

    def __init__(self):
        """Inicializa monitor"""
        self.metrics = {
            "request_times": [],
            "model_times": [],
            "parsing_times": [],
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def start_timer(self) -> float:
        """Inicia timer, retorna timestamp"""
        return time.time()

    def end_timer(self, start_time: float, metric_type: str = "request_times") -> float:
        """Termina timer e registra métrica. Retorna tempo decorrido em ms."""
        elapsed_ms = (time.time() - start_time) * 1000
        if metric_type in self.metrics and isinstance(self.metrics[metric_type], list):
            self.metrics[metric_type].append(elapsed_ms)
            # Manter apenas últimas 100 entradas para não usar muita memória
            if len(self.metrics[metric_type]) > 100:
                self.metrics[metric_type] = self.metrics[metric_type][-100:]
        return elapsed_ms

    def get_average_time(self, metric_type: str = "request_times") -> float:
        """Retorna tempo médio para métrica em ms"""
        if metric_type in self.metrics and isinstance(self.metrics[metric_type], list):
            times = self.metrics[metric_type]
            return sum(times) / len(times) if times else 0
        return 0

    def record_cache_event(self, hit: bool) -> None:
        """Registra evento de cache hit/miss"""
        if hit:
            self.metrics["cache_hits"] += 1
        else:
            self.metrics["cache_misses"] += 1

    def get_report(self) -> str:
        """Retorna relatório formatado de performance"""
        avg_request = self.get_average_time("request_times")
        avg_model = self.get_average_time("model_times")
        total_requests = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        hit_rate = (self.metrics["cache_hits"] / total_requests * 100) if total_requests > 0 else 0.0

        report = f"""
[PERFORMANCE REPORT]
==================
Tempo médio de requisição: {avg_request:.1f}ms
Tempo médio de modelo: {avg_model:.1f}ms
Total de requisições: {total_requests}
Cache hits: {self.metrics["cache_hits"]}
Cache misses: {self.metrics["cache_misses"]}
Taxa de acerto de cache: {hit_rate:.1f}%
==================
"""
        return report.strip()


if __name__ == "__main__":
    # Teste do cache e otimizador
    cache = SmartCache()
    optimizer = ResponseOptimizer()
    monitor = PerformanceMonitor()

    # Teste de cache
    print("[TEST] Testando cache inteligente...")
    cache.set("qual é a capital da França?", "Paris é a capital da França.", confidence=0.95)
    cache.set("como fazer bolo?", "Misture farinha, ovos e açúcar...", confidence=0.8)

    # Testa recuperação
    result = cache.get("qual é a capital da França?")
    print(f"Cache hit: {result is not None}")
    if result:
        print(f"  Resposta: {result['response'][:50]}...")

    # Teste de otimizador
    print("\n[TEST] Testando otimizador de respostas...")
    hints = optimizer.get_optimization_hints("qual é a capital da França?", is_question=True, confidence=0.9)
    print(f"Otimizações sugeridas: {hints}")

    # Cache stats
    print(f"\n[STATS] Cache: {cache.get_stats()}")
