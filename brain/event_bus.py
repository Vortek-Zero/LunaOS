#!/usr/bin/env python3
"""
brain/event_bus.py — Barramento de Eventos (Event Bus) da Luna
Permite comunicação desacoplada entre componentes (memória, hábitos, rotinas, etc.).
"""
import logging
import threading
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger("luna.event_bus")

class EventBus:
    """
    Barramento de Eventos Publish-Subscribe thread-safe.
    Permite publicar eventos e reagir a eles de forma assíncrona/concorrente.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

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
        em threads separadas para não bloquear o emissor.
        """
        logger.info(f"Evento publicado: {event_type}")
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for cb in callbacks:
            # Roda cada callback em uma thread separada para manter assincronismo
            t = threading.Thread(
                target=self._safe_execute, 
                args=(cb, event_type, data), 
                daemon=True
            )
            t.start()

    def _safe_execute(self, callback: Callable[[Any], None], event_type: str, data: Any) -> None:
        try:
            callback(data)
        except Exception as e:
            logger.error(f"Erro ao executar callback do evento {event_type}: {e}", exc_info=True)


# Singleton
_event_bus_instance: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance
