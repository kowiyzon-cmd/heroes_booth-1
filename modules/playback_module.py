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
from datetime import datetime

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
    """Класс для воспроизведения видео"""
    
    def __init__(self):
        self.is_playing = False
        self.current_process = None
        
    def play_video(self, video_path, timeout=30):
        """Воспроизвести видеофайл"""
        try:
            logger.info(f"🔍 Пытаюсь воспроизвести видео: {video_path}")
            
            # Проверяем существование файла
            if not os.path.exists(video_path):
                logger.error(f"❌ Видеофайл не найден: {video_path}")
                return False
            
            logger.info(f"✅ Видеофайл найден: {video_path} ({os.path.getsize(video_path)} байт)")
            
            # Используем omxplayer
            cmd = ["omxplayer", "-o", "hdmi", video_path]
            logger.info(f"🚀 Запускаю команду: {' '.join(cmd)}")
            
            # Запускаем процесс
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.is_playing = True
            
            # Ждем завершения с таймаутом
            try:
                return_code = self.current_process.wait(timeout=timeout)
                
                if return_code == 0:
                    logger.info("✅ Воспроизведение видео завершено успешно")
                    return True
                else:
                    logger.error(f"❌ Видеоплеер завершился с кодом ошибки: {return_code}")
                    return False
                    
            except subprocess.TimeoutExpired:
                logger.error(f"❌ Воспроизведение видео превысило таймаут {timeout} секунд")
                self.current_process.terminate()
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения видео: {e}")
            return False
        finally:
            self.is_playing = False
    
    def stop_playback(self):
        """Остановить воспроизведение"""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
            except:
                pass
            finally:
                self.is_playing = False

class SimpleGUI:
    """Упрощенный GUI - показывает только текст в консоли"""
    
    def __init__(self):
        self.is_showing = False
        
    def show_recording_interface(self, current_question, total_questions, hero_name):
        """Показать интерфейс записи (текстовый)"""
        print("\n" + "=" * 60)
        print(f"🎤 ЗАДАЙТЕ ВОПРОС ГЕРОЮ")
        print(f"👤 Герой: {hero_name}")
        print(f"📝 Вопрос {current_question} из {total_questions}")
        print("=" * 60)
        print("🎤 ГОВОРИТЕ СЕЙЧАС...")
        for i in range(3, 0, -1):
            print(f"⏳ Обратный отсчет: {i}...")
            time.sleep(1)
        self.is_showing = True
        
    def hide_recording_interface(self):
        """Скрыть интерфейс записи"""
        print("✅ Запись завершена")
        print("=" * 60 + "\n")
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
        logger.info(f"🚀 Начинаю сессию для {self.hero_name}")
        
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
                # Ждем вместо воспроизведения видео
                time.sleep(5)
                continue
            
            # Отправляем аудио на сервер
            logger.info(f"📤 Отправляю аудио на сервер...")
            video_path = self.send_audio_to_server(audio_file, question_num)
            
            # Удаляем временный аудиофайл
            try:
                if os.path.exists(audio_file):
                    os.unlink(audio_file)
            except:
                pass
            
            # Воспроизводим полученное видео
            if video_path and os.path.exists(video_path):
                logger.info(f"🎬 Воспроизвожу полученное видео: {video_path}")
                success = self.video_player.play_video(video_path)
                
                # Удаляем временный видеофайл
                if video_path.startswith('/tmp/'):
                    try:
                        os.unlink(video_path)
                    except:
                        pass
            else:
                logger.info("⏳ Ожидаю 5 секунд (видео не получено)")
                time.sleep(5)
        
        logger.info(f"✅ Сессия завершена для {self.hero_name}")
        return self.session_history
    
    def send_audio_to_server(self, audio_file_path, question_num):
        """Отправить аудиофайл на Django сервер и получить видео"""
        try:
            api_url = f"{DJANGO_URL}/subcategory/{self.subcategory_id}/ask/"
            logger.info(f"🌐 Отправляю аудио на {api_url}")
            
            if not os.path.exists(audio_file_path):
                logger.error(f"❌ Аудиофайл не существует: {audio_file_path}")
                return None
            
            # Подготавливаем данные для отправки
            with open(audio_file_path, 'rb') as audio_file:
                files = {'audio': (f'question_{question_num}.wav', audio_file, 'audio/wav')}
                data = {'hero_name': self.hero_name, 'language': self.language}
                
                # Отправляем POST запрос
                response = requests.post(api_url, files=files, data=data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info("✅ Аудио успешно отправлено")
                    
                    # Получаем путь к видео
                    video_path = result.get('video')
                    if video_path:
                        logger.info(f"🎬 Получен путь к видео: {video_path}")
                        return self.download_video_if_needed(video_path)
                    
                logger.error(f"❌ Ошибка сервера: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке аудио: {e}")
        
        return None
    
    def download_video_if_needed(self, video_path):
        """Скачать видео если это URL"""
        try:
            # Если это URL - скачиваем
            if video_path.startswith('http'):
                temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                temp_video_path = temp_video.name
                temp_video.close()
                
                logger.info(f"📥 Скачиваю видео с {video_path}")
                response = requests.get(video_path, stream=True, timeout=30)
                
                if response.status_code == 200:
                    with open(temp_video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if os.path.getsize(temp_video_path) > 0:
                        return temp_video_path
                        
            # Если это локальный путь
            elif os.path.exists(video_path):
                return video_path
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки видео: {e}")
        
        return None

class PlaybackModule:
    """Основной модуль воспроизведения"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.gui = SimpleGUI()
        self.audio_recorder = AudioRecorder()
        self.video_player = VideoPlayer()
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
            
            # 1. Воспроизводим приветственное видео (ТОЛЬКО ОДИН РАЗ)
            logger.info("🎬 Воспроизвожу приветственное видео...")
            self.play_greeting_video()
            
            # 2. Запускаем сессии для каждого героя
            for hero_name in heroes:
                if not self.playback_active:
                    break
                    
                logger.info(f"🎭 Начинаю сессию для героя: {hero_name}")
                
                session = PlaybackSession(
                    hero_name=hero_name,
                    language='ru',
                    subcategory_id=subcategory_id,
                    base_url=DJANGO_URL,
                    gui_controller=self.gui,
                    audio_recorder=self.audio_recorder,
                    video_player=self.video_player
                )
                
                session.run_session()
                logger.info(f"✅ Сессия для героя {hero_name} завершена")
            
            # 3. Воспроизводим завершающее видео (ТОЛЬКО ОДИН РАЗ)
            if self.playback_active:
                logger.info("🎬 Воспроизвожу завершающее видео...")
                self.play_ending_video()
            
            # 4. Публикуем событие завершения
            logger.info("✅ Процесс воспроизведения завершен")
            self.publish_playback_finished(heroes)
            
        except Exception as e:
            logger.error(f"❌ Ошибка процесса воспроизведения: {e}")
            self.publish_playback_error(str(e))
        finally:
            self.playback_active = False
    
    def play_greeting_video(self):
        """Воспроизвести приветственное видео (ОДИН РАЗ)"""
        greeting_paths = [
            "media/greet_video.mp4",
            "greet_video.mp4",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "greet_video.mp4")
        ]
        
        for path in greeting_paths:
            if os.path.exists(path):
                logger.info(f"🎬 Воспроизвожу приветственное видео: {path}")
                # Воспроизводим ОДИН РАЗ и выходим
                success = self.video_player.play_video(path)
                if not success:
                    logger.error(f"❌ Не удалось воспроизвести приветственное видео")
                return
        
        logger.error("❌ Приветственное видео не найдено")
    
    def play_ending_video(self):
        """Воспроизвести завершающее видео (ОДИН РАЗ)"""
        ending_paths = [
            "media/end_video.mp4",
            "end_video.mp4",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "end_video.mp4")
        ]
        
        for path in ending_paths:
            if os.path.exists(path):
                logger.info(f"🎬 Воспроизвожу завершающее видео: {path}")
                # Воспроизводим ОДИН РАЗ и выходим
                success = self.video_player.play_video(path)
                if not success:
                    logger.error(f"❌ Не удалось воспроизвести завершающее видео")
                return
        
        logger.error("❌ Завершающее видео не найдено")
    
    def publish_playback_finished(self, heroes):
        """Публикация события завершения воспроизведения"""
        try:
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
            self.event_bus.publish("playback_error", {
                "error": error_message,
                "timestamp": time.time(),
                "message": "Ошибка воспроизведения"
            })
        except Exception as e:
            logger.error(f"❌ Ошибка публикации события: {e}")
    
    def stop_playback(self):
        """Экстренная остановка воспроизведения"""
        self.playback_active = False
        self.video_player.stop_playback()

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
    
    # Проверяем наличие omxplayer
    try:
        result = subprocess.run(["which", "omxplayer"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ omxplayer найден: {result.stdout.strip()}")
        else:
            logger.error("❌ omxplayer не найден!")
            logger.error("Установите: sudo apt-get install omxplayer")
    except:
        pass
    
    # Проверяем видеофайлы
    for video in ["media/greet_video.mp4", "media/end_video.mp4"]:
        if os.path.exists(video):
            logger.info(f"✅ Видео найдено: {video} ({os.path.getsize(video)} байт)")
        else:
            logger.warning(f"⚠️ Видео не найдено: {video}")
    
    # Получаем данные из аргументов
    if len(sys.argv) > 1:
        try:
            heroes_data = json.loads(sys.argv[1])
            logger.info(f"📦 Получены данные героев")
            
            if isinstance(heroes_data, list):
                processed_data = {'hero_names': heroes_data, 'subcategory_id': 13}
            else:
                processed_data = heroes_data
                
        except:
            logger.error("❌ Ошибка парсинга данных")
            processed_data = {'hero_names': ['Test'], 'subcategory_id': 13}
    else:
        logger.warning("⚠️ Данные не предоставлены, использую тестовые")
        processed_data = {'hero_names': ['Test'], 'subcategory_id': 13}
    
    # Создаем и запускаем модуль
    event_bus = EventBus()
    playback_module = PlaybackModule(event_bus)
    
    # Запускаем воспроизведение
    playback_module.start_playback(processed_data)
    
    logger.info("🏁 Модуль воспроизведения завершил работу")

if __name__ == "__main__":
    main()