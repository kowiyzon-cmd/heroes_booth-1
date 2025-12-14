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

try:
    import sounddevice as sd
    import soundfile as sf
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

from event_bus import EventBus
from config import BASE_URL  # Используем BASE_URL вместо DJANGO_URL

logger = logging.getLogger(__name__)

class AudioRecorder:
    """Класс для записи аудио"""
    
    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        
    def record_audio(self, duration=3):
        """Записать аудио указанной длительности"""
        if not SOUND_AVAILABLE:
            logger.error("❌ sounddevice/soundfile не установлены")
            # Создаем заглушку для тестирования
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_file = f.name
                logger.info(f"⚠️ Создаю заглушку аудиофайла: {temp_file}")
                return temp_file
                
        try:
            logger.info(f"🎤 Начинаю запись аудио на {duration} секунд...")
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
                logger.info(f"✅ Аудио записано: {temp_file}")
                return temp_file
                
        except Exception as e:
            logger.error(f"❌ Ошибка записи аудио: {e}")
            self.is_recording = False
            return None

class VideoPlayer:
    """Класс для воспроизведения видео с использованием mpv"""
    
    def __init__(self):
        self.is_playing = False
        self.current_process = None
        
    def play_video(self, video_path, timeout=60):
        """Воспроизвести видеофайл используя mpv"""
        try:
            logger.info(f"🔍 Пытаюсь воспроизвести видео: {video_path}")
            
            # Проверяем существование файла
            if not os.path.exists(video_path):
                logger.error(f"❌ Видеофайл не найден: {video_path}")
                
                # Пробуем найти в media директории
                base_name = os.path.basename(video_path)
                alt_path = os.path.join("media", base_name)
                if os.path.exists(alt_path):
                    video_path = alt_path
                    logger.info(f"✅ Нашел видео по альтернативному пути: {video_path}")
                else:
                    logger.error("❌ Видео не найдено ни по одному из путей")
                    return False
            
            file_size = os.path.getsize(video_path)
            logger.info(f"✅ Видеофайл найден: {video_path} ({file_size} байт)")
            
            # Проверяем доступность mpv
            try:
                result = subprocess.run(["which", "mpv"], capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error("❌ mpv не найден!")
                    # Пробуем другие плееры как fallback
                    return self.try_alternative_player(video_path, timeout)
            except Exception as e:
                logger.error(f"❌ Не удалось проверить наличие mpv: {e}")
                return self.try_alternative_player(video_path, timeout)
            
            # Используем mpv с настройками для киоска
            cmd = ["mpv", "--fs", "--no-input-default-bindings", video_path]
            logger.info(f"🚀 Запускаю mpv: {' '.join(cmd)}")
            
            # Запускаем процесс
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.is_playing = True
            
            # Мониторим вывод для дебага
            def monitor_output():
                try:
                    while self.current_process and self.current_process.poll() is None:
                        try:
                            # Читаем stdout
                            stdout_line = self.current_process.stdout.readline()
                            if stdout_line:
                                if "Video file loaded" in stdout_line or "Playing:" in stdout_line:
                                    logger.info(f"MPV: {stdout_line.strip()}")
                                else:
                                    logger.debug(f"MPV: {stdout_line.strip()}")
                            
                            # Читаем stderr
                            stderr_line = self.current_process.stderr.readline()
                            if stderr_line:
                                logger.warning(f"MPV ERR: {stderr_line.strip()}")
                        except:
                            break
                except Exception as e:
                    logger.debug(f"Ошибка мониторинга вывода mpv: {e}")
            
            monitor_thread = threading.Thread(target=monitor_output, daemon=True)
            monitor_thread.start()
            
            # Даем время для запуска
            time.sleep(1)
            
            # Проверяем что процесс запустился
            if self.current_process.poll() is not None:
                logger.error("❌ mpv завершился сразу после запуска")
                return_code = self.current_process.returncode
                logger.error(f"Код возврата: {return_code}")
                
                # Пробуем получить ошибку
                try:
                    stderr_output = self.current_process.stderr.read()
                    if stderr_output:
                        logger.error(f"Ошибка mpv: {stderr_output[:500]}")
                except:
                    pass
                return False
            
            logger.info("✅ mpv успешно запущен, ожидаю завершения воспроизведения...")
            
            # Ждем завершения с таймаутом
            try:
                return_code = self.current_process.wait(timeout=timeout)
                
                if return_code == 0:
                    logger.info("✅ Воспроизведение видео завершено успешно")
                    return True
                else:
                    logger.warning(f"⚠️ mpv завершился с кодом: {return_code}")
                    # Для mpv не всегда 0 означает успех, иногда может быть 1 но видео показано
                    return True  # Все равно считаем успехом если видео было показано
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ Воспроизведение превысило таймаут {timeout} секунд")
                # Для длинных видео это нормально
                if self.current_process:
                    self.current_process.terminate()
                    try:
                        self.current_process.wait(timeout=2)
                    except:
                        pass
                return True  # Считаем что видео было показано
                
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения видео: {e}")
            return False
        finally:
            self.is_playing = False
    
    def try_alternative_player(self, video_path, timeout):
        """Попробовать другие видеоплееры"""
        alternative_players = [
            ("vlc", ["vlc", "--fullscreen", "--play-and-exit", "--no-video-title-show", video_path]),
            ("cvlc", ["cvlc", "--fullscreen", "--play-and-exit", "--no-video-title-show", video_path]),
            ("omxplayer", ["omxplayer", "-o", "hdmi", video_path]),
        ]
        
        for player_name, cmd in alternative_players:
            try:
                result = subprocess.run(["which", player_name], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"🔄 Пробую использовать {player_name}")
                    self.current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    
                    self.is_playing = True
                    
                    # Ждем завершения
                    try:
                        return_code = self.current_process.wait(timeout=timeout)
                        if return_code == 0:
                            logger.info(f"✅ {player_name} успешно воспроизвел видео")
                            return True
                    except subprocess.TimeoutExpired:
                        self.current_process.terminate()
                        return True
                        
            except Exception as e:
                logger.debug(f"Ошибка с {player_name}: {e}")
                continue
        
        logger.error("❌ Ни один видеоплеер не доступен")
        return False
    
    def stop_playback(self):
        """Остановить воспроизведение"""
        if self.current_process and self.current_process.poll() is None:
            try:
                logger.info("⏹ Останавливаю воспроизведение...")
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
                logger.info("✅ Воспроизведение остановлено")
            except Exception as e:
                logger.error(f"❌ Ошибка при остановке воспроизведения: {e}")
            finally:
                self.is_playing = False

class SimpleGUI:
    """Упрощенный GUI для интерфейса записи"""
    
    def __init__(self):
        self.is_showing = False
        
    def show_recording_interface(self, current_question, total_questions, hero_name):
        """Показать интерфейс записи"""
        print("\n" + "=" * 60)
        print(f"🎤 ЗАДАЙТЕ ВОПРОС ГЕРОЮ")
        print(f"👤 Герой: {hero_name}")
        print(f"📝 Вопрос {current_question} из {total_questions}")
        print("=" * 60)
        print("🎤 ГОВОРИТЕ СЕЙЧАС...")
        print("⏳ 3...")
        time.sleep(1)
        print("⏳ 2...")
        time.sleep(1)
        print("⏳ 1...")
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
        logger.info(f"🚀 Начинаю сессию для героя: {self.hero_name}")
        
        for question_num in range(1, self.question_count + 1):
            logger.info(f"❓ Вопрос {question_num}/{self.question_count} для {self.hero_name}")
            
            # Показываем интерфейс записи
            self.gui.show_recording_interface(question_num, self.question_count, self.hero_name)
            
            # Записываем аудио (3 секунды)
            audio_file = self.audio_recorder.record_audio(duration=3)
            
            # Скрываем интерфейс записи
            self.gui.hide_recording_interface()
            
            if not audio_file or not os.path.exists(audio_file):
                logger.error(f"❌ Не удалось записать аудио для вопроса {question_num}")
                # Показываем заглушку 5 секунд
                logger.info("⏳ Показываю заглушку 5 секунд...")
                time.sleep(5)
                continue
            
            logger.info(f"📤 Отправляю аудио на сервер...")
            
            # Отправляем аудио на сервер
            video_response = self.send_audio_to_server(audio_file, question_num)
            
            # Удаляем временный аудиофайл
            try:
                if os.path.exists(audio_file):
                    os.unlink(audio_file)
                    logger.debug(f"🗑 Удалил аудиофайл: {audio_file}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить аудиофайл: {e}")
            
            # Воспроизводим полученное видео
            if video_response and os.path.exists(video_response):
                logger.info(f"🎬 Воспроизвожу видео ответ: {video_response}")
                success = self.video_player.play_video(video_response, timeout=30)
                
                # Удаляем временный видеофайл если он был скачан
                if video_response.startswith('/tmp/'):
                    try:
                        os.unlink(video_response)
                        logger.debug(f"🗑 Удалил временное видео: {video_response}")
                    except:
                        pass
                        
                if not success:
                    logger.warning(f"⚠️ Не удалось воспроизвести видео, показываю заглушку")
                    time.sleep(5)
            else:
                logger.warning("⚠️ Не получено видео от сервера, показываю заглушку")
                time.sleep(5)
        
        logger.info(f"✅ Сессия завершена для героя: {self.hero_name}")
        return self.session_history
    
    def send_audio_to_server(self, audio_file_path, question_num):
        """Отправить аудиофайл на сервер и получить видео"""
        try:
            # Формируем URL для отправки аудио
            api_url = f"{self.base_url}/subcategory/{self.subcategory_id}/ask/"
            logger.info(f"🌐 Отправляю аудио на: {api_url}")
            
            if not os.path.exists(audio_file_path):
                logger.error(f"❌ Аудиофайл не существует: {audio_file_path}")
                return None
            
            file_size = os.path.getsize(audio_file_path)
            logger.info(f"📁 Размер аудиофайла: {file_size} байт")
            
            # Подготавливаем данные для отправки
            with open(audio_file_path, 'rb') as audio_file:
                files = {
                    'audio': (f'question_{question_num}_{self.hero_name}.wav', audio_file, 'audio/wav')
                }
                
                data = {
                    'hero_name': self.hero_name,
                    'language': self.language
                }
                
                # Отправляем POST запрос
                logger.info(f"📤 Отправляю POST запрос...")
                response = requests.post(
                    api_url,
                    files=files,
                    data=data,
                    timeout=30
                )
                
                logger.info(f"📥 Ответ сервера: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info("✅ Аудио успешно отправлено на сервер")
                    
                    # Получаем путь к видео
                    video_path = result.get('video')
                    if video_path:
                        logger.info(f"🎬 Получен путь к видео: {video_path}")
                        return self.process_video_path(video_path)
                    else:
                        logger.warning("⚠️ Сервер не вернул путь к видео")
                        # Проверяем другие возможные поля
                        if 'fastapi_data' in result:
                            fastapi_data = result['fastapi_data']
                            if 'video' in fastapi_data:
                                video_path = fastapi_data['video']
                                logger.info(f"🎬 Получен путь к видео из fastapi_data: {video_path}")
                                return self.process_video_path(video_path)
                else:
                    logger.error(f"❌ Ошибка сервера: {response.status_code}")
                    logger.error(f"Текст ответа: {response.text[:200]}")
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети при отправке аудио: {e}")
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {e}")
        
        return None
    
    def process_video_path(self, video_path):
        """Обработать путь к видео: скачать если это URL"""
        try:
            # Если это полный URL
            if video_path.startswith('http'):
                # Скачиваем видео во временный файл
                temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                temp_video_path = temp_video.name
                temp_video.close()
                
                logger.info(f"📥 Скачиваю видео с {video_path}")
                
                response = requests.get(video_path, stream=True, timeout=30)
                if response.status_code == 200:
                    total_size = 0
                    with open(temp_video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                total_size += len(chunk)
                    
                    logger.info(f"✅ Видео скачано: {temp_video_path} ({total_size} байт)")
                    return temp_video_path
                else:
                    logger.error(f"❌ Ошибка скачивания: {response.status_code}")
                    return None
            
            # Если это путь от /media/
            elif video_path.startswith('/media/'):
                # Пробуем найти локально
                local_path = video_path.replace('/media/', 'media/')
                if os.path.exists(local_path):
                    logger.info(f"✅ Нашел локальное видео: {local_path}")
                    return local_path
                
                # Пробуем скачать с сервера
                full_url = f"{self.base_url}{video_path}"
                logger.info(f"🔄 Пробую скачать по полному URL: {full_url}")
                return self.process_video_path(full_url)
            
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
            logger.info("🚀 ЗАПУСКАЮ ПРОЦЕСС ВОСПРОИЗВЕДЕНИЯ")
            self.playback_active = True
            
            # Получаем данные
            heroes = heroes_data.get('hero_names', [])
            subcategory_id = heroes_data.get('subcategory_id')
            
            logger.info(f"🎭 Герои для обработки: {heroes}")
            logger.info(f"🔢 ID подкатегории: {subcategory_id}")
            logger.info(f"🌐 Базовый URL: {BASE_URL}")
            
            # 1. Воспроизводим приветственное видео
            logger.info("🎬 ШАГ 1: Приветственное видео...")
            greeting_success = self.play_greeting_video()
            
            if not greeting_success:
                logger.warning("⚠️ Не удалось воспроизвести приветственное видео")
                logger.info("⏳ Ожидаю 5 секунд...")
                time.sleep(5)
            
            # 2. Запускаем сессии для каждого героя
            logger.info("🎬 ШАГ 2: Запускаю сессии героев...")
            for hero_index, hero_name in enumerate(heroes, 1):
                if not self.playback_active:
                    logger.info("⏹ Воспроизведение остановлено")
                    break
                
                logger.info(f"🎭 [{hero_index}/{len(heroes)}] Начинаю сессию для: {hero_name}")
                
                # Создаем сессию для героя
                session = PlaybackSession(
                    hero_name=hero_name,
                    language='ru',
                    subcategory_id=subcategory_id,
                    base_url=BASE_URL,
                    gui_controller=self.gui,
                    audio_recorder=self.audio_recorder,
                    video_player=self.video_player
                )
                
                # Запускаем сессию (6 вопросов)
                session.run_session()
                logger.info(f"✅ [{hero_index}/{len(heroes)}] Сессия завершена: {hero_name}")
            
            # 3. Воспроизводим завершающее видео
            if self.playback_active:
                logger.info("🎬 ШАГ 3: Завершающее видео...")
                ending_success = self.play_ending_video()
                
                if not ending_success:
                    logger.warning("⚠️ Не удалось воспроизвести завершающее видео")
                    logger.info("⏳ Ожидаю 5 секунд...")
                    time.sleep(5)
            
            # 4. Публикуем событие завершения
            logger.info("✅ ПРОЦЕСС ВОСПРОИЗВЕДЕНИЯ ЗАВЕРШЕН")
            self.publish_playback_finished(heroes)
            
        except KeyboardInterrupt:
            logger.info("🛑 Прервано пользователем")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в процессе воспроизведения: {e}")
            self.publish_playback_error(str(e))
        finally:
            self.playback_active = False
    
    def play_greeting_video(self):
        """Воспроизвести приветственное видео"""
        greeting_paths = [
            "media/greet_video.mp4",
            "greet_video.mp4",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "greet_video.mp4")
        ]
        
        for path in greeting_paths:
            if os.path.exists(path):
                logger.info(f"🎬 Воспроизвожу приветственное видео: {path}")
                return self.video_player.play_video(path, timeout=30)
        
        logger.error("❌ Приветственное видео не найдено")
        return False
    
    def play_ending_video(self):
        """Воспроизвести завершающее видео"""
        ending_paths = [
            "media/end_video.mp4",
            "end_video.mp4",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "end_video.mp4")
        ]
        
        for path in ending_paths:
            if os.path.exists(path):
                logger.info(f"🎬 Воспроизвожу завершающее видео: {path}")
                return self.video_player.play_video(path, timeout=30)
        
        logger.error("❌ Завершающее видео не найдено")
        return False
    
    def publish_playback_finished(self, heroes):
        """Публикация события завершения воспроизведения"""
        try:
            logger.info("📤 Публикую событие playback_finished")
            self.event_bus.publish("playback_finished", {
                "heroes": heroes,
                "timestamp": time.time(),
                "message": "Воспроизведение завершено успешно"
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
        logger.info("🛑 Экстренная остановка воспроизведения")
        self.playback_active = False
        self.video_player.stop_playback()

def check_system():
    """Проверка системы перед запуском"""
    logger.info("🔧 ПРОВЕРКА СИСТЕМЫ")
    logger.info("=" * 50)
    
    # Проверяем mpv
    try:
        result = subprocess.run(["which", "mpv"], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ mpv найден: {result.stdout.strip()}")
            
            # Проверяем версию mpv
            version_result = subprocess.run(["mpv", "--version"], capture_output=True, text=True)
            if version_result.returncode == 0:
                first_line = version_result.stdout.split('\n')[0]
                logger.info(f"📊 Версия mpv: {first_line}")
        else:
            logger.error("❌ mpv не найден!")
            logger.info("Установите: sudo apt-get install mpv")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки mpv: {e}")
        return False
    
    # Проверяем видеофайлы
    logger.info("\n🔍 Проверяю видеофайлы:")
    required_videos = ["media/greet_video.mp4", "media/end_video.mp4"]
    
    all_found = True
    for video in required_videos:
        if os.path.exists(video):
            size = os.path.getsize(video)
            logger.info(f"✅ {video} - {size} байт")
        else:
            logger.error(f"❌ {video} не найден")
            all_found = False
    
    if not all_found:
        logger.warning("⚠️ Некоторые видеофайлы отсутствуют")
    
    # Проверяем звук
    if not SOUND_AVAILABLE:
        logger.warning("⚠️ sounddevice/soundfile не установлены")
        logger.info("Установите: pip install sounddevice soundfile")
    
    logger.info("=" * 50)
    return True

def main():
    """Точка входа для запуска как отдельного процесса"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger.info("=" * 60)
    logger.info("🚀 МОДУЛЬ ВОСПРОИЗВЕДЕНИЯ - СТАРТ")
    logger.info("=" * 60)
    logger.info(f"🌐 Базовый URL: {BASE_URL}")
    logger.info(f"📁 Текущая директория: {os.getcwd()}")
    
    # Проверяем систему
    check_system()
    
    # Получаем данные из аргументов
    processed_data = None
    if len(sys.argv) > 1:
        try:
            raw_data = sys.argv[1]
            logger.info(f"📦 Получены сырые данные: {raw_data[:100]}...")
            
            heroes_data = json.loads(raw_data)
            logger.info(f"✅ Данные успешно распарсены")
            
            # Проверяем формат данных
            if isinstance(heroes_data, list):
                processed_data = {
                    'hero_names': heroes_data,
                    'subcategory_id': 13
                }
                logger.info("🔄 Преобразовано из списка в словарь")
            else:
                processed_data = heroes_data
                
            logger.info(f"🎭 Герои: {processed_data.get('hero_names', [])}")
            logger.info(f"🔢 ID подкатегории: {processed_data.get('subcategory_id')}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка JSON: {e}")
            logger.error(f"Сырые данные: {sys.argv[1][:200]}")
            processed_data = {'hero_names': ['Test_Hero'], 'subcategory_id': 13}
        except Exception as e:
            logger.error(f"❌ Ошибка обработки данных: {e}")
            processed_data = {'hero_names': ['Test_Hero'], 'subcategory_id': 13}
    else:
        logger.warning("⚠️ Данные не предоставлены в аргументах")
        logger.info("Использую тестовые данные для отладки")
        processed_data = {
            'hero_names': ['Test_Hero_1', 'Test_Hero_2'],
            'subcategory_id': 13
        }
    
    # Создаем и запускаем модуль
    try:
        event_bus = EventBus()
        playback_module = PlaybackModule(event_bus)
        
        # Запускаем воспроизведение
        playback_module.start_playback(processed_data)
        
        logger.info("🏁 Модуль воспроизведения завершил работу")
        
    except KeyboardInterrupt:
        logger.info("🛑 Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    main()