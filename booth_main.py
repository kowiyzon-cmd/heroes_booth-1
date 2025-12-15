#!/usr/bin/env python3
# booth_main.py - Главный модуль кабинки воспроизведения
import logging
import sys
import time
import threading
import json
import subprocess
import os
from typing import List, Dict

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('booth')

# Импортируем существующие модули
from event_bus import EventBus
from gpio_manager import GPIOManager
from media_manager import MediaManager
from qr_scanner import QRScanner

# Добавляем путь для импорта playback_module
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

class BoothController:
    """Главный контроллер кабинки воспроизведения"""
    
    def __init__(self):
        self.event_bus = EventBus()
        self.gpio = GPIOManager(self.event_bus)
        self.media = MediaManager()
        self.qr_scanner = QRScanner(self.event_bus)
        
        self.current_session = None
        self.session_active = False
        self.playback_process = None
        
        self.setup_event_handlers()
        
    def setup_event_handlers(self):
        """Настройка обработчиков событий"""
        self.event_bus.subscribe("qr_valid", self.on_qr_valid)
        self.event_bus.subscribe("playback_finished", self.on_playback_finished)
        self.event_bus.subscribe("playback_error", self.on_playback_error)
        self.event_bus.subscribe("motion_cleared", self.on_motion_cleared)
        
    def on_qr_valid(self, data):
        """Обработка валидного QR-кода"""
        logger.info("✅ Valid QR code received and payment verified")
        
        # Останавливаем сканирование QR-кодов
        self.qr_scanner.stop_scanning()
        
        # Извлекаем данные из QR
        qr_data = data.get('heroes', {})
        
        # Проверяем валидность платежа
        if self.validate_payment(qr_data):
            logger.info("Payment validated, starting session")
            self.start_session(qr_data)
        else:
            logger.warning("Invalid payment data")
            # Если платеж не прошел, возобновляем сканирование
            self.start_qr_scanning()
            
    def validate_payment(self, payment_data: Dict) -> bool:
        """Проверить валидность платежа"""
        try:
            # Уже проверено в QR сканере, но делаем дополнительную проверку
            payment_id = payment_data.get('payment_id')
            
            # Проверяем наличие необходимых данных для воспроизведения
            if payment_data.get('hero_names') and isinstance(payment_data.get('hero_names'), list):
                logger.info(f"Valid payment data for heroes: {payment_data.get('hero_names')}")
                return True
                
            logger.warning("Invalid payment data structure")
            return False
            
        except Exception as e:
            logger.error(f"Payment validation error: {e}")
            return False
    
    def start_session(self, session_data: Dict):
        """Начать сеанс в кабинке"""
        if self.session_active:
            logger.warning("Session already active")
            return
            
        self.session_active = True
        self.current_session = session_data
        
        logger.info(f"🎬 Starting booth session: {session_data}")
        
        # Открываем дверь и включаем свет
        self.gpio.set_door_state(True)
        self.gpio.set_light_state(True)
        
        # Запускаем воспроизведение через существующий playback_module
        self.start_playback_module(session_data)
        
    def start_playback_module(self, session_data: Dict):
        """Запустить модуль воспроизведения"""
        try:
            logger.info(f"Starting playback module with data: {session_data}")
            
            # Подготавливаем данные для playback_module в том же формате, что в main.py
            playback_data = {
                'hero_names': session_data.get('hero_names', []),
                'subcategory_id': session_data.get('subcategory_id', 13),
                'total_videos': len(session_data.get('hero_names', [])),
                'timestamp': time.time()
            }
            
            logger.info(f"Playback data: {playback_data}")
            
            # Запускаем существующий playback_module как отдельный процесс
            cmd = [
                sys.executable, 
                "modules/playback_module.py",
                json.dumps(playback_data)
            ]
            
            logger.info(f"Starting playback command: {' '.join(cmd)}")
            
            self.playback_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info("Playback module started")
            
            # Мониторим вывод процесса для дебага
            self.monitor_playback_output()
            
            # Мониторим процесс воспроизведения
            self.monitor_playback_process()
            
        except Exception as e:
            logger.error(f"❌ Failed to start playback module: {e}")
            self.event_bus.publish("playback_error", {
                "error": str(e),
                "timestamp": time.time()
            })
    
    def monitor_playback_output(self):
        """Мониторинг вывода playback процесса для дебага"""
        def _monitor_output():
            try:
                while self.playback_process and self.playback_process.poll() is None:
                    # Читаем stdout
                    stdout_line = self.playback_process.stdout.readline()
                    if stdout_line:
                        logger.info(f"PLAYBACK: {stdout_line.strip()}")
                    
                    # Читаем stderr
                    stderr_line = self.playback_process.stderr.readline()
                    if stderr_line:
                        print(self.playback_process.stderr.readlines())
                        logger.error(f"PLAYBACK ERROR: {stderr_line.strip()}")
                        
            except Exception as e:
                logger.error(f"Playback output monitoring error: {e}")
        
        output_thread = threading.Thread(target=_monitor_output, daemon=True)
        output_thread.start()
    
    def monitor_playback_process(self):
        """Мониторинг процесса воспроизведения"""
        def _monitor():
            try:
                # Ждем завершения процесса воспроизведения
                return_code = self.playback_process.wait()
                
                if return_code == 0:
                    logger.info("✅ Playback process completed successfully")
                    self.event_bus.publish("playback_finished", {
                        "timestamp": time.time(),
                        "session": self.current_session
                    })
                else:
                    logger.error(f"❌ Playback process failed with code: {return_code}")
                    self.event_bus.publish("playback_error", {
                        "error": f"Process exit code: {return_code}",
                        "timestamp": time.time()
                    })
                    
            except Exception as e:
                logger.error(f"Playback monitoring error: {e}")
        
        # Запускаем мониторинг в отдельном потоке
        monitor_thread = threading.Thread(target=_monitor, daemon=True)
        monitor_thread.start()
    
    def on_playback_finished(self, data):
        """Обработка завершения воспроизведения"""
        logger.info("✅ Playback finished successfully")
        
        # Закрываем дверь и выключаем свет после выхода пользователя
        self.gpio.check_motion_and_cleanup()
        
    def on_playback_error(self, data):
        """Обработка ошибки воспроизведения"""
        logger.error(f"❌ Playback error: {data.get('error')}")
        
        # Все равно пытаемся очистить кабинку
        self.gpio.check_motion_and_cleanup()
    
    def on_motion_cleared(self, data):
        """Обработка очистки движения"""
        logger.info("Motion cleared, resetting booth")
        self.reset_booth()
    
    def reset_booth(self):
        """Сбросить состояние кабинки"""
        logger.info("Resetting booth state")
        
        # Останавливаем процесс воспроизведения если он еще работает
        if self.playback_process and self.playback_process.poll() is None:
            logger.info("Stopping playback process")
            self.playback_process.terminate()
            try:
                self.playback_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.playback_process.kill()
        
        self.session_active = False
        self.current_session = None
        self.playback_process = None
        
        # Даем небольшую задержку перед запуском сканирования
        time.sleep(1)
        
        # Начинаем ожидание нового QR-кода
        self.start_qr_scanning()
    
    def start_qr_scanning(self):
        """Начать сканирование QR-кодов"""
        logger.info("📷 Starting QR code scanning")
        
        # Используем resume_scanning вместо прямого вызова start_scanning
        # чтобы корректно управлять состоянием сканера
        if not self.qr_scanner.scanning:
            qr_thread = threading.Thread(target=self.qr_scanner.start_scanning, daemon=True)
            qr_thread.start()
        else:
            logger.warning("QR scanner already active")
    
    def run(self):
        """Запуск кабинки"""
        logger.info("Starting Booth System")
        
        try:
            # Запускаем обработку событий
            event_bus_thread = threading.Thread(target=self.event_bus.start, daemon=True)
            event_bus_thread.start()
            
            # Проверяем наличие необходимых видеофайлов
            self.check_video_files()
            
            # Начинаем сканирование QR-кодов
            self.start_qr_scanning()
            
            # Основной цикл
            logger.info("✅ Booth system ready. Waiting for QR codes...")
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Booth interrupted by user")
        except Exception as e:
            logger.error(f"Booth error: {e}")
        finally:
            self.shutdown()
    
    def check_video_files(self):
        """Проверить наличие необходимых видеофайлов"""
        logger.info("🔍 Checking video files...")
        
        # Проверяем приветственное видео
        greeting_path = "media/greet_video.mp4"
        if os.path.exists(greeting_path):
            logger.info(f"✅ Greeting video found: {greeting_path}")
        else:
            logger.warning(f"⚠️ Greeting video not found: {greeting_path}")
        
        # Проверяем завершающее видео
        ending_path = "media/end_video.mp4"
        if os.path.exists(ending_path):
            logger.info(f"✅ Ending video found: {ending_path}")
        else:
            logger.warning(f"⚠️ Ending video not found: {ending_path}")
        
        # Проверяем папку с видео героев
        heroes_path = "media/hero_videos"
        if os.path.exists(heroes_path):
            hero_count = len([f for f in os.listdir(heroes_path) if os.path.isdir(os.path.join(heroes_path, f))])
            logger.info(f"✅ Hero videos folder found with {hero_count} heroes")
        else:
            logger.warning(f"⚠️ Hero videos folder not found: {heroes_path}")
            
    def shutdown(self):
        """Корректное завершение"""
        logger.info("Shutting down booth...")
        
        # Останавливаем все процессы
        if self.playback_process and self.playback_process.poll() is None:
            self.playback_process.terminate()
        
        self.event_bus.stop()
        self.qr_scanner.stop_scanning()
        self.gpio.cleanup()

if __name__ == "__main__":
    booth = BoothController()
    booth.run()
