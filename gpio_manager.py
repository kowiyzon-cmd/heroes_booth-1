import logging
import time
import threading
from config import DOOR_PIN, LIGHT_PIN, MOTION_SENSOR_PIN
from event_bus import EventBus

logger = logging.getLogger(__name__)

class GPIOManager:
    """Менеджер GPIO для управления оборудованием кабинки"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.door_pin = DOOR_PIN
        self.light_pin = LIGHT_PIN
        self.motion_pin = MOTION_SENSOR_PIN
        
        # Состояния
        self.session_active = False
        self.door_open = False
        self.light_on = False
        self.motion_detected = False
        
        self._setup_event_handlers()
        logger.info("GPIO менеджер инициализирован (режим заглушки)")
        
    def _setup_event_handlers(self):
        """Настройка обработчиков событий"""
        self.event_bus.subscribe("qr_valid", self.on_qr_valid)
        self.event_bus.subscribe("playback_finished", self.on_playback_finished)
        self.event_bus.subscribe("playback_error", self.on_playback_error)
        self.event_bus.subscribe("motion_cleared", self.on_motion_cleared)
        logger.info("Обработчики событий настроены")
        
    def on_qr_valid(self, data):
        """Обработка валидного QR-кода - начало сессии"""
        logger.info("QR-код подтвержден, начинаем сессию")
        self.session_active = True
        logger.info("Сессия активна: %s", self.session_active)
        self.set_door_state(True)
        self.set_light_state(True)
        
    def on_playback_finished(self, data):
        """Обработка завершения трансляции"""
        logger.info("Воспроизведение завершено, начинаем процедуру очистки")
        self.session_active = False
        logger.info("Сессия активна: %s", self.session_active)
        
        # Даем пользователю время выйти
        logger.info("Ожидаем 3 секунды перед проверкой движения")
        time.sleep(3)
        
        # В режиме заглушки всегда считаем что движения нет
        # и сразу очищаем кабинку
        logger.info("Режим заглушки: движение не проверяется, очищаем кабинку")
        self.cleanup()
        
    def on_playback_error(self, data):
        """Обработка ошибки воспроизведения"""
        logger.error("Ошибка воспроизведения: %s", data.get('error'))
        self.session_active = False
        logger.info("Сессия активна: %s", self.session_active)
        self.cleanup()
        
    def on_motion_cleared(self, data):
        """Обработка очистки движения"""
        logger.info("Получено событие очистки движения")
        # В режиме заглушки просто логируем
        pass
        
    def set_door_state(self, open_state: bool):
        """Управление дверьми"""
        try:
            if open_state:
                self.door_open = True
                logger.info("Дверь: ОТКРЫТА (заглушка)")
            else:
                self.door_open = False
                logger.info("Дверь: ЗАКРЫТА (заглушка)")
        except Exception as e:
            logger.error("Ошибка управления дверью: %s", e)
        
    def set_light_state(self, on_state: bool):
        """Управление освещением"""
        try:
            if on_state:
                self.light_on = True
                logger.info("Свет: ВКЛЮЧЕН (заглушка)")
            else:
                self.light_on = False
                logger.info("Свет: ВЫКЛЮЧЕН (заглушка)")
        except Exception as e:
            logger.error("Ошибка управления светом: %s", e)
        
    def check_motion_sensor(self) -> bool:
        """Проверить датчик движения"""
        try:
            # В режиме заглушки всегда возвращаем False
            # чтобы система сразу очищала кабинку
            motion = False
            self.motion_detected = motion
            logger.info("Состояние датчика движения: движения нет (заглушка)")
            return motion
        except Exception as e:
            logger.error("Ошибка проверки датчика движения: %s", e)
            return False
        
    def check_motion_and_cleanup(self):
        """Проверить движение и выполнить cleanup"""
        logger.info("Проверяем наличие движения в кабинке (заглушка)")
        
        # В режиме заглушки всегда очищаем
        logger.info("Режим заглушки: очищаем кабинку без проверки движения")
        self.cleanup()
            
    def cleanup(self):
        """Выключить все и закрыть двери"""
        logger.info("Начинаем очистку кабинки")
        self.set_light_state(False)
        time.sleep(1)  # Даем время свету выключиться
        self.set_door_state(False)
        logger.info("Очистка кабинки завершена")
        
        # Публикуем событие для возобновления сканирования QR
        logger.info("Отправляем событие об очистке движения")
        self.event_bus.publish("motion_cleared", {
            "timestamp": time.time(),
            "message": "Кабинка очищена и готова к новой сессии (заглушка)"
        })
    
    def cleanup_gpio(self):
        """Корректно освободить GPIO ресурсы"""
        try:
            logger.info("GPIO ресурсы освобождены (заглушка)")
        except Exception as e:
            logger.error("Ошибка освобождения GPIO ресурсов: %s", e)
