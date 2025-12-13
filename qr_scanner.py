import time
import logging
import json
import threading
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from event_bus import EventBus

# Создаем отдельный логгер для QR сканера
qr_logger = logging.getLogger('qr_scanner')

class QRScanner:
    """Сканер QR-кодов для кабинки"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.scanning = False
        self.camera = None
        self.scan_thread = None
        
        # Обязательные поля для валидации QR-данных
        self.required_fields = ['hero_names', 'subcategory_id', 'timestamp', 'type']
        
    def start_scanning(self):
        """Начать сканирование QR-кода в кабинке"""
        if self.scanning:
            qr_logger.warning("QR scanning already active")
            return
            
        qr_logger.info("Starting QR code scanning in booth...")
        self.scanning = True
        
        # Запускаем сканирование в отдельном потоке
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()
        
    def _scan_loop(self):
        """Основной цикл сканирования"""
        try:
            # Инициализируем камеру
            self.camera = self._initialize_camera()
            if self.camera is None:
                qr_logger.error("Failed to initialize camera, stopping scanner")
                self.scanning = False
                return
                
            qr_logger.info("🎥 Camera initialized, starting QR scanning...")
            last_scan_time = 0
            scan_cooldown = 2  # секунды между сканированиями одного QR
            
            while self.scanning:
                try:
                    # Читаем кадр с камеры
                    ret, frame = self.camera.read()
                    if not ret:
                        qr_logger.warning("Failed to capture frame from camera")
                        time.sleep(0.1)
                        continue
                    
                    # Уменьшаем разрешение для ускорения обработки
                    small_frame = cv2.resize(frame, (640, 480))
                    
                    # Декодируем QR-коды
                    decoded_objects = decode(small_frame)
                    
                    current_time = time.time()
                    
                    for obj in decoded_objects:
                        try:
                            qr_data = obj.data.decode('utf-8')
                            qr_logger.info(f"🔍 QR code detected: {qr_data[:50]}...")
                            
                            # Проверяем cooldown чтобы не обрабатывать один QR многократно
                            if current_time - last_scan_time < scan_cooldown:
                                qr_logger.debug("QR cooldown active, skipping")
                                continue
                            
                            # Парсим JSON данные из QR-кода
                            parsed_data = json.loads(qr_data)
                            qr_logger.info(f"Parsed QR data: {parsed_data}")
                            
                            # Валидируем данные
                            if self.validate_qr_structure(parsed_data):
                                # Проверяем платеж
                                if self.verify_payment(parsed_data):
                                    qr_logger.info("✅ QR data validated and payment verified")
                                    self.process_valid_qr(parsed_data)
                                    last_scan_time = current_time
                                    break  # Прерываем обработку текущего кадра
                                else:
                                    qr_logger.warning("❌ Payment verification failed")
                            else:
                                qr_logger.warning(f"❌ Invalid QR structure. Required fields: {self.required_fields}")
                                
                        except json.JSONDecodeError as e:
                            qr_logger.warning(f"Invalid JSON in QR: {e}")
                        except UnicodeDecodeError:
                            qr_logger.warning("Failed to decode QR data as UTF-8")
                        except Exception as e:
                            qr_logger.error(f"Error processing QR: {e}")
                    
                    # Отображаем кадр для отладки (можно отключить в production)
                    cv2.imshow('QR Scanner - Press Q to quit', small_frame)
                    
                    # Проверяем нажатие клавиши 'q' для выхода (только для отладки)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        qr_logger.info("QR scanning stopped by user")
                        self.stop_scanning()
                        break
                        
                except Exception as e:
                    qr_logger.error(f"Error in scan loop: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            qr_logger.error(f"Fatal error in scan loop: {e}")
        finally:
            self._cleanup_camera()
            
    def _initialize_camera(self):
        """Инициализировать камеру"""
        try:
            # Пробуем разные индексы камер (0-3)
            for camera_index in range(4):
                try:
                    qr_logger.info(f"Trying to open camera index {camera_index}...")
                    cap = cv2.VideoCapture(camera_index)
                    
                    # Пробуем получить кадр для проверки
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            qr_logger.info(f"✅ Camera {camera_index} initialized successfully")
                            # Настраиваем параметры камеры для лучшего сканирования
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                            cap.set(cv2.CAP_PROP_FPS, 30)
                            return cap
                        else:
                            cap.release()
                except:
                    continue
                    
            qr_logger.error("No camera found on indices 0-3")
            return None
            
        except Exception as e:
            qr_logger.error(f"Camera initialization error: {e}")
            return None
            
    def _cleanup_camera(self):
        """Освободить ресурсы камеры"""
        if self.camera is not None:
            try:
                self.camera.release()
                cv2.destroyAllWindows()
                qr_logger.info("Camera resources released")
            except:
                pass
            finally:
                self.camera = None
                
    def validate_qr_structure(self, qr_data: dict) -> bool:
        """Проверить структуру данных QR-кода"""
        try:
            # Проверяем наличие всех обязательных полей
            for field in self.required_fields:
                if field not in qr_data:
                    qr_logger.warning(f"Missing required field: {field}")
                    return False
            
            # Дополнительные проверки типов данных
            if not isinstance(qr_data.get('hero_names'), list):
                qr_logger.warning("hero_names must be a list")
                return False
                
            if not isinstance(qr_data.get('subcategory_id'), int):
                qr_logger.warning("subcategory_id must be an integer")
                return False
                
            if not isinstance(qr_data.get('timestamp'), (int, float)):
                qr_logger.warning("timestamp must be a number")
                return False
                
            if qr_data.get('type') != 'heroes_selection':
                qr_logger.warning(f"Invalid type: {qr_data.get('type')}")
                return False
                
            return True
            
        except Exception as e:
            qr_logger.error(f"Validation error: {e}")
            return False
            
    def verify_payment(self, qr_data: dict) -> bool:
        """Проверить платеж через API (заглушка)"""
        try:
            # ЗАГЛУШКА: API проверки платежа
            # В реальной реализации здесь будет HTTP запрос к платежной системе
            
            # Пример проверки дополнительных полей платежа
            payment_id = qr_data.get('payment_id')
            amount = qr_data.get('amount')
            
            # Временная заглушка - всегда возвращаем True
            qr_logger.info(f"✅ Payment verified (stub). Payment ID: {payment_id}, Amount: {amount}")
            return True
            
            # Реализация API запроса (пример):
            # import requests
            # api_url = "https://payment-system.example.com/verify"
            # response = requests.post(api_url, json={
            #     'payment_id': payment_id,
            #     'amount': amount,
            #     'timestamp': qr_data.get('timestamp')
            # })
            # return response.status_code == 200 and response.json().get('verified', False)
            
        except Exception as e:
            qr_logger.error(f"Payment verification error: {e}")
            return False
            
    def process_valid_qr(self, qr_data: dict):
        """Обработать валидный QR-код"""
        qr_logger.info(f"Processing valid QR data: {qr_data}")
        
        # Останавливаем сканирование
        self.scanning = False
        
        # Публикуем событие с данными QR-кода
        self.event_bus.publish("qr_valid", {
            "heroes": qr_data,
            "timestamp": time.time(),
            "message": "QR code validated and payment verified"
        })
        
    def stop_scanning(self):
        """Остановить сканирование"""
        if not self.scanning:
            return
            
        qr_logger.info("Stopping QR scanning...")
        self.scanning = False
        
        # Ждем завершения потока сканирования
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=2.0)
            
        self._cleanup_camera()
        qr_logger.info("QR scanning stopped")
        
    def resume_scanning(self):
        """Возобновить сканирование после завершения сессии"""
        qr_logger.info("Resuming QR scanning after session completion")
        if not self.scanning:
            self.start_scanning()
