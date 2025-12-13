import multiprocessing
import queue
import time
from typing import Any, Callable, Dict, List
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """Шина событий для межпроцессного взаимодействия"""
    
    def __init__(self):
        self._event_queue = multiprocessing.Queue()
        self._subscribers: Dict[str, List[Callable]] = {}
        self._running = multiprocessing.Event()
        
    def subscribe(self, event_type: str, callback: Callable):
        """Подписаться на событие"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"Подписан на {event_type}")
        
    def unsubscribe(self, event_type: str, callback: Callable):
        """Отписаться от события"""
        if event_type in self._subscribers:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                
    def publish(self, event_type: str, data: Any = None):
        """Опубликовать событие"""
        logger.info(f"Опубликовано событие: {event_type}. Данные: {data}")
        self._event_queue.put((event_type, data))
        
    def start(self):
        """Запустить обработку событий"""
        self._running.set()
        while self._running.is_set():
            try:
                event_type, data = self._event_queue.get(timeout=1.0)
                if event_type in self._subscribers:
                    for callback in self._subscribers[event_type]:
                        try:
                            callback(data)
                        except Exception as e:
                            logger.error(f"Ошибка в хендлере события: {e}")
            except queue.Empty:
                continue
                
    def stop(self):
        """Остановить обработку событий"""
        self._running.clear()
