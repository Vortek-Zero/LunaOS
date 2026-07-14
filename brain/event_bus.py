#!/usr/bin/env python3
"""
brain/event_bus.py — Barramento de Eventos (Event Bus) da Luna
Permite comunicação desacoplada entre componentes (memória, hábitos, rotinas, etc.).
"""

import atexit
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger("luna.event_bus")

# Pool compartilhado — reutiliza threads ao invés de criar/destruir por evento
_MAX_WORKERS = 5


class EventBus:
    """
    Barramento de Eventos Publish-Subscribe thread-safe.
    Utiliza ThreadPoolExecutor para evitar thread thrashing sob carga alta.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="eventbus")
        atexit.register(self._shutdown)

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Inscreve um callback para um tipo de evento."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.debug(f"Inscrição registrada para o evento: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Remove a inscrição de um callback."""
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                logger.debug(f"Inscrição removida para o evento: {event_type}")

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Publica um evento, disparando todos os callbacks inscritos
        via ThreadPoolExecutor para não bloquear o emissor.
        """
        logger.info(f"Evento publicado: {event_type}")
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for cb in callbacks:
            self._pool.submit(self._safe_execute, cb, event_type, data)

    def _safe_execute(self, callback: Callable[[Any], None], event_type: str, data: Any) -> None:
        try:
            callback(data)
        except Exception as e:
            logger.error(f"Erro ao executar callback do evento {event_type}: {e}", exc_info=True)

    def _shutdown(self) -> None:
        """Desliga o pool de threads de forma limpa ao encerrar o processo."""
        self._pool.shutdown(wait=False)


# Singleton
_event_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance
