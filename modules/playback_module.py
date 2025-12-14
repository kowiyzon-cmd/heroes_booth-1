# modules/playback_module.py
import time
import logging
import sys
import os
import json
import requests
import tempfile
import threading
import subprocess
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import sounddevice as sd
import soundfile as sf
from datetime import datetime
import multiprocessing as mp

# Добавляем путь к корневой директории для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_bus import EventBus
from config import DJANGO_URL  # Импортируем URL из config.py

logger = logging.getLogger(__name__)

class AudioRecorder:
    """Класс для записи аудио"""
    
    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.recording_data = None
        
    def record_audio(self, duration=3):
        """Записать аудио указанной длительности"""
        try:
            logger.info(f"Начинаю запись аудио на {duration} секунд...")
            self.is_recording = True
            
            # Записываем аудио
            recording = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32'
            )
            
            # Ждем завершения записи
            sd.wait()
            self.is_recording = False
            
            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_file = f.name
                sf.write(temp_file, recording, self.sample_rate)
                logger.info(f"✅ Аудио записано и сохранено в {temp_file}")
                return temp_file
                
        except Exception as e:
            logger.error(f"❌ Ошибка записи аудио: {e}")
            self.is_recording = False
            return None

class VideoPlayer:
    """Класс для воспроизведения видео - УПРОЩЕННАЯ ВЕРСИЯ"""
    
    def __init__(self):
        self.is_playing = False
        self.current_process = None
        
    def play_video(self, video_path):
        """Воспроизвести видеофайл - ПРОСТАЯ БЛОКИРУЮЩАЯ ВЕРСИЯ"""
        try:
            logger.info(f"🔍 Пытаюсь воспроизвести видео: {video_path}")
            
            # Проверяем существование файла
            if not os.path.exists(video_path):
                logger.error(f"❌ Видеофайл не найден: {video_path}")
                # Пробуем найти в других местах
                alt_paths = [
                    video_path,
                    os.path.join("media", os.path.basename(video_path)),
                    os.path.join(os.path.dirname(__file__), "..", video_path),
                    os.path.abspath(video_path)
                ]
                
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        video_path = alt_path
                        logger.info(f"✅ Нашел видео по альтернативному пути: {video_path}")
                        break
                else:
                    logger.error(f"❌ Видео не найдено ни по одному из путей")
                    return False
            
            logger.info(f"✅ Видеофайл найден: {video_path} ({os.path.getsize(video_path)} байт)")
            
            # ПРОСТАЯ КОМАНДА - только mpv
            cmd = ["mpv", "--fs", "--no-input-default-bindings", video_path]
            logger.info(f"🚀 Запускаю команду: {' '.join(cmd)}")
            
            # Запускаем процесс и ждем его завершения
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Мониторим вывод
            def monitor():
                while process.poll() is None:
                    try:
                        stdout = process.stdout.readline()
                        stderr = process.stderr.readline()
                        if stdout:
                            logger.debug(f"mpv: {stdout.strip()}")
                        if stderr:
                            logger.debug(f"mpv ERR: {stderr.strip()}")
                    except:
                        pass
            
            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()
            
            # Ждем завершения
            return_code = process.wait()
            
            if return_code == 0:
                logger.info("✅ Воспроизведение видео завершено успешно")
                return True
            else:
                logger.error(f"❌ Видеоплеер завершился с кодом ошибки: {return_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения видео: {e}")
            return False
    
    def stop_playback(self):
        """Остановить воспроизведение"""
        logger.info("⏹ Останавливаю воспроизведение видео...")
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
                logger.info("✅ Воспроизведение остановлено")
            except:
                logger.warning("⚠️ Не удалось корректно остановить воспроизведение")

class SimpleGUI:
    """Упрощенный GUI - показывает только текст в консоли"""
    
    def __init__(self):
        self.is_showing = False
        
    def show_recording_interface(self, current_question, total_questions, hero_name):
        """Показать интерфейс записи (текстовый)"""
        logger.info("=" * 60)
        logger.info(f"🎤 ЗАДАЙТЕ ВОПРОС ГЕРОЮ")
        logger.info(f"👤 Герой: {hero_name}")
        logger.info(f"📝 Вопрос {current_question} из {total_questions}")
        logger.info("=" * 60)
        logger.info("🎤 ГОВОРИТЕ СЕЙЧАС...")
        logger.info("⏳ Обратный отсчет: 3...")
        time.sleep(1)
        logger.info("⏳ Обратный отсчет: 2...")
        time.sleep(1)
        logger.info("⏳ Обратный отсчет: 1...")
        time.sleep(1)
        self.is_showing = True
        
    def hide_recording_interface(self):
        """Скрыть интерфейс записи"""
        logger.info("✅ Запись завершена")
        logger.info("=" * 60)
        self.is_showing = False

class PlaybackSession:
    """Сессия воспроизведения для одного героя"""
    
    def __init__(self, hero_name, language, subcategory_id, base_url, gui_controller, audio_recorder, video_player):
        self.hero_name = hero_name
        self.language = language
        self.subcategory_id = subcategory_id
        self.base_url = base_url
        self.gui = gui_controller
        self.audio_recorder = audio_recorder
        self.video_player = video_player
        self.question_count = 6
        self.session_history = []
        
    def run_session(self):
        """Запустить сессию вопросов для героя"""
        logger.info(f"🚀 Начинаю сессию для {self.hero_name} на языке {self.language}")
        
        for question_num in range(1, self.question_count + 1):
            logger.info(f"❓ Вопрос {question_num}/{self.question_count} для {self.hero_name}")
            
            # Показываем интерфейс записи
            self.gui.show_recording_interface(question_num, self.question_count, self.hero_name)
            
            # Записываем аудио
            audio_file = self.audio_recorder.record_audio(duration=3)
            
            # Скрываем интерфейс записи
            self.gui.hide_recording_interface()
            
            if not audio_file:
                logger.error(f"❌ Не удалось записать аудио для вопроса {question_num}")
                # Воспроизводим заглушку
                self.play_fallback_video()
                continue
            
            # Отправляем аудио на сервер и получаем видео для воспроизведения
            logger.info(f"📤 Отправляю аудио на сервер...")
            video_path = self.send_audio_to_server(audio_file, question_num)
            
            # Удаляем временный аудиофайл
            try:
                if os.path.exists(audio_file):
                    os.unlink(audio_file)
                    logger.info(f"✅ Аудиофайл удален: {audio_file}")
            except Exception as e:
                logger.error(f"❌ Ошибка удаления аудиофайла: {e}")
            
            # Если получили видео - воспроизводим
            if video_path:
                logger.info(f"🎬 Получено видео для воспроизведения: {video_path}")
                success = self.video_player.play_video(video_path)
                
                # Удаляем временный видеофайл если он был скачан
                if video_path.startswith('/tmp/'):
                    try:
                        os.unlink(video_path)
                        logger.info(f"✅ Временный видеофайл удален: {video_path}")
                    except:
                        pass
                
                # Сохраняем в историю сессии
                self.session_history.append({
                    'question_number': question_num,
                    'hero_name': self.hero_name,
                    'language': self.language,
                    'audio_sent': True,
                    'video_played': success,
                    'video_source': video_path,
                    'timestamp': datetime.now().isoformat()
                })
                
                if not success:
                    logger.error(f"❌ Не удалось воспроизвести видео для вопроса {question_num}")
                    self.play_fallback_video()
            else:
                logger.error(f"❌ Не удалось получить видео для вопроса {question_num}")
                # Воспроизводим заглушку
                self.play_fallback_video()
                
                self.session_history.append({
                    'question_number': question_num,
                    'hero_name': self.hero_name,
                    'language': self.language,
                    'audio_sent': video_path is not None,
                    'video_played': False,
                    'video_source': 'fallback',
                    'timestamp': datetime.now().isoformat()
                })
        
        logger.info(f"✅ Сессия завершена для {self.hero_name}")
        return self.session_history
    
    def send_audio_to_server(self, audio_file_path, question_num):
        """Отправить аудиофайл на Django сервер и получить видео"""
        try:
            # URL для отправки аудио (из config.py)
            django_url = DJANGO_URL
            api_url = f"{django_url}/subcategory/{self.subcategory_id}/ask/"
            logger.info(f"🌐 Отправляю аудио на {api_url}")
            logger.info(f"📁 Аудиофайл: {audio_file_path} ({os.path.getsize(audio_file_path)} байт)")
            
            # Проверяем существование файла
            if not os.path.exists(audio_file_path):
                logger.error(f"❌ Аудиофайл не существует: {audio_file_path}")
                return None
            
            # Подготавливаем данные для отправки
            with open(audio_file_path, 'rb') as audio_file:
                files = {
                    'audio': (f'question_{question_num}.wav', audio_file, 'audio/wav')
                }
                
                data = {
                    'hero_name': self.hero_name,
                    'language': self.language
                }
                
                # Отправляем POST запрос
                logger.info(f"📤 Отправляю POST запрос с данными: {data}")
                response = requests.post(
                    api_url,
                    files=files,
                    data=data,
                    timeout=30
                )
                
                logger.info(f"📥 Получен ответ от сервера: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Аудио успешно отправлено")
                    
                    # Получаем путь к видео из ответа
                    video_path = result.get('video')
                    if video_path:
                        logger.info(f"🎬 Получен путь к видео: {video_path}")
                        # Пробуем скачать если нужно
                        return self.try_get_video(video_path)
                    else:
                        logger.warning("⚠️ Сервер не вернул путь к видео в ответе")
                        return None
                else:
                    logger.error(f"❌ Ошибка сервера: {response.status_code}")
                    logger.error(f"Текст ответа: {response.text[:500]}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети при отправке аудио: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при отправке аудио: {e}")
            return None
    
    def try_get_video(self, video_path):
        """Попытаться получить видео по пути"""
        try:
            # Если это URL - скачиваем
            if video_path.startswith('http'):
                return self.download_video(video_path)
            # Если это локальный путь
            elif os.path.exists(video_path):
                return video_path
            # Если это путь от /media/
            elif video_path.startswith('/media/'):
                local_path = video_path.replace('/media/', 'media/')
                if os.path.exists(local_path):
                    return local_path
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения видео: {e}")
            return None
    
    def download_video(self, url):
        """Скачать видео с URL"""
        try:
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            temp_video_path = temp_video.name
            temp_video.close()
            
            logger.info(f"📥 Скачиваю видео с {url}")
            response = requests.get(url, stream=True, timeout=30)
            
            if response.status_code == 200:
                with open(temp_video_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                file_size = os.path.getsize(temp_video_path)
                if file_size > 0:
                    logger.info(f"✅ Видео скачано: {temp_video_path} ({file_size} байт)")
                    return temp_video_path
                else:
                    logger.error("❌ Скачанный файл пустой")
                    os.unlink(temp_video_path)
                    return None
            else:
                logger.error(f"❌ Не удалось скачать видео: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания видео: {e}")
            return None
    
    def play_fallback_video(self):
        """Воспроизвести видео-заглушку при ошибке"""
        logger.info("🔄 Пытаюсь воспроизвести видео-заглушку...")
        
        # Пробуем найти любое доступное видео
        test_videos = [
            "media/greet_video.mp4",
            "media/end_video.mp4",
            "greet_video.mp4",
            "end_video.mp4"
        ]
        
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        test_videos.extend([
            os.path.join(current_dir, "media", "greet_video.mp4"),
            os.path.join(current_dir, "media", "end_video.mp4"),
        ])
        
        for video_path in test_videos:
            if os.path.exists(video_path):
                logger.info(f"✅ Нашел видео для теста: {video_path}")
                success = self.video_player.play_video(video_path)
                return success
        
        # Если видео нет, просто ждем
        logger.warning("⚠️ Видео не найдены, ожидаем 5 секунд")
        time.sleep(5)
        return False

class PlaybackModule:
    """Основной модуль воспроизведения"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.gui = SimpleGUI()  # Упрощенный GUI
        self.audio_recorder = AudioRecorder()
        self.video_player = VideoPlayer()
        self.full_history = []
        self.playback_active = False
        
    def start_playback(self, heroes_data: dict):
        """Начать полный процесс воспроизведения"""
        try:
            logger.info("🚀 Запускаю процесс воспроизведения")
            self.playback_active = True
            
            # Получаем данные
            heroes = heroes_data.get('hero_names', [])
            subcategory_id = heroes_data.get('subcategory_id')
            
            logger.info(f"🎭 Обрабатываю {len(heroes)} героев: {heroes}")
            logger.info(f"🔢 ID подкатегории: {subcategory_id}")
            
            # 1. Воспроизводим приветственное видео
            logger.info("🎬 Воспроизвожу приветственное видео...")
            if not self.test_video_playback():
                logger.error("❌ Не удалось воспроизвести тестовое видео!")
                # Но продолжаем всё равно
            
            # 2. Запускаем сессии для каждого героя
            for hero_name in heroes:
                if not self.playback_active:
                    logger.info("⏹ Воспроизведение остановлено")
                    break
                    
                logger.info(f"🎭 Начинаю сессию для героя: {hero_name}")
                
                # Для каждого героя создаем сессию
                session = PlaybackSession(
                    hero_name=hero_name,
                    language='ru',
                    subcategory_id=subcategory_id,
                    base_url=DJANGO_URL,
                    gui_controller=self.gui,
                    audio_recorder=self.audio_recorder,
                    video_player=self.video_player
                )
                
                # Запускаем сессию вопросов
                session_history = session.run_session()
                self.full_history.extend(session_history)
                logger.info(f"✅ Сессия для героя {hero_name} завершена")
            
            # 3. Воспроизводим завершающее видео
            if self.playback_active:
                logger.info("🎬 Воспроизвожу завершающее видео...")
                self.test_video_playback()
            
            # 4. Публикуем событие завершения
            logger.info("✅ Процесс воспроизведения завершен")
            self.publish_playback_finished(heroes)
            
        except Exception as e:
            logger.error(f"❌ Ошибка процесса воспроизведения: {e}", exc_info=True)
            self.publish_playback_error(str(e))
        finally:
            self.playback_active = False
    
    def test_video_playback(self):
        """Тестируем воспроизведение видео"""
        # Пробуем найти и воспроизвести любое доступное видео
        test_videos = [
            "media/greet_video.mp4",
            "media/end_video.mp4"
        ]
        
        for video_path in test_videos:
            if os.path.exists(video_path):
                logger.info(f"🔍 Тестирую воспроизведение: {video_path}")
                success = self.video_player.play_video(video_path)
                if success:
                    logger.info(f"✅ Тестовое видео успешно воспроизведено: {video_path}")
                    return True
                else:
                    logger.error(f"❌ Не удалось воспроизвести тестовое видео: {video_path}")
        
        logger.error("❌ Не найдено ни одного тестового видеофайла")
        return False
    
    def publish_playback_finished(self, heroes):
        """Публикация события завершения воспроизведения"""
        try:
            logger.info("📤 Публикую событие playback_finished")
            self.event_bus.publish("playback_finished", {
                "heroes": heroes,
                "timestamp": time.time(),
                "message": "Воспроизведение завершено"
            })
        except Exception as e:
            logger.error(f"❌ Ошибка публикации события: {e}")
    
    def publish_playback_error(self, error_message):
        """Публикация события ошибки"""
        try:
            logger.info("📤 Публикую событие playback_error")
            self.event_bus.publish("playback_error", {
                "error": error_message,
                "timestamp": time.time(),
                "message": "Ошибка воспроизведения"
            })
        except Exception as e:
            logger.error(f"❌ Ошибка публикации события: {e}")
    
    def stop_playback(self):
        """Экстренная остановка воспроизведения"""
        logger.info("🛑 Останавливаю воспроизведение")
        self.playback_active = False
        self.video_player.stop_playback()

def test_video_player():
    """Тестируем видеоплеер отдельно"""
    logger.info("🔧 Тестирую видеоплеер...")
    
    # Проверяем доступность omxplayer
    try:
        result = subprocess.run(["which", "omxplayer"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ omxplayer найден: {result.stdout.strip()}")
        else:
            logger.error("❌ omxplayer не найден!")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки omxplayer: {e}")
        return False
    
    # Пробуем найти тестовое видео
    test_videos = [
        "media/greet_video.mp4",
        "media/end_video.mp4",
        "test_video.mp4"
    ]
    
    found_video = None
    for video in test_videos:
        if os.path.exists(video):
            found_video = video
            logger.info(f"✅ Нашел тестовое видео: {video}")
            break
    
    if not found_video:
        logger.error("❌ Не найдено ни одного тестового видеофайла")
        logger.info("Создаю тестовое видео командой...")
        
        # Создаем простой тестовый видеофайл с помощью ffmpeg
        try:
            test_cmd = [
                "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=5:size=640x480:rate=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "test_video.mp4"
            ]
            logger.info(f"Создаю тестовое видео: {' '.join(test_cmd)}")
            subprocess.run(test_cmd, capture_output=True)
            found_video = "test_video.mp4"
        except Exception as e:
            logger.error(f"❌ Не удалось создать тестовое видео: {e}")
            return False
    
    # Пробуем воспроизвести
    logger.info(f"🎬 Пробую воспроизвести: {found_video}")
    player = VideoPlayer()
    success = player.play_video(found_video)
    
    if success:
        logger.info("✅ Видеоплеер работает корректно!")
    else:
        logger.error("❌ Видеоплеер не смог воспроизвести видео")
    
    return success

def main():
    """Точка входа для запуска как отдельного процесса"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger.info("=" * 50)
    logger.info("🚀 Запуск модуля воспроизведения")
    logger.info("=" * 50)
    logger.info(f"🌐 Django URL: {DJANGO_URL}")
    
    # Сначала тестируем видеоплеер
    if not test_video_player():
        logger.error("❌ ПРЕДУПРЕЖДЕНИЕ: Видеоплеер не работает корректно!")
        logger.error("❌ Проверьте: sudo apt-get install omxplayer")
        logger.error("❌ И наличие видеофайлов в media/")
    
    # Получаем данные из аргументов командной строки
    if len(sys.argv) > 1:
        try:
            heroes_data = json.loads(sys.argv[1])
            logger.info(f"📦 Получены данные героев")
            
            # Проверяем структуру данных
            if isinstance(heroes_data, list):
                processed_data = {
                    'hero_names': heroes_data,
                    'subcategory_id': 13
                }
            else:
                processed_data = heroes_data
                
            logger.info(f"🎭 Герои: {processed_data.get('hero_names', [])}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга данных героев: {e}")
            sys.exit(1)
    else:
        # ТЕСТОВЫЕ ДАННЫЕ для отладки
        logger.warning("⚠️ Данные не предоставлены, использую тестовые данные")
        processed_data = {
            'hero_names': ['Test_Hero'],
            'subcategory_id': 13
        }
    
    # Создаем и запускаем модуль
    event_bus = EventBus()
    playback_module = PlaybackModule(event_bus)
    
    # Запускаем воспроизведение в основном потоке
    playback_module.start_playback(processed_data)
    
    logger.info("🏁 Модуль воспроизведения завершил работу")

if __name__ == "__main__":
    main()