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
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import sounddevice as sd
import soundfile as sf
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
                logger.info(f"Аудио записано и сохранено в {temp_file}")
                return temp_file
                
        except Exception as e:
            logger.error(f"Ошибка записи аудио: {e}")
            self.is_recording = False
            return None

class VideoPlayer:
    """Класс для воспроизведения видео"""
    
    def __init__(self):
        self.is_playing = False
        self.current_process = None
        
    def play_video(self, video_path):
        """Воспроизвести видеофайл"""
        try:
            if not os.path.exists(video_path):
                logger.error(f"Видеофайл не найден: {video_path}")
                return False
                
            logger.info(f"Воспроизвожу видео: {video_path}")
            self.is_playing = True
            
            # Используем простой плеер
            video_players = [
                ("/usr/bin/omxplayer", ["omxplayer", "-o", "hdmi", "--no-keys", "--no-osd", video_path]),
                ("/usr/bin/vlc", ["vlc", "--fullscreen", "--play-and-exit", "--no-video-title-show", video_path]),
                ("/usr/bin/mpv", ["mpv", "--fs", "--no-input-default-bindings", video_path]),
                ("cvlc", ["cvlc", "--fullscreen", "--play-and-exit", "--no-video-title-show", video_path])
            ]
            
            cmd = None
            for player_path, player_cmd in video_players:
                if os.path.exists(player_path) or subprocess.run(["which", player_path.split('/')[-1]], capture_output=True).returncode == 0:
                    cmd = player_cmd
                    logger.info(f"Использую видеоплеер: {player_path}")
                    break
            
            if not cmd:
                logger.error("Видеоплеер не найден. Установите omxplayer, vlc или mpv.")
                return False
            
            logger.info(f"Запускаю команду: {' '.join(cmd)}")
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Ждем завершения воспроизведения
            return_code = self.current_process.wait()
            self.is_playing = False
            
            if return_code == 0:
                logger.info("Воспроизведение видео завершено успешно")
                return True
            else:
                logger.error(f"Видеоплеер завершился с кодом: {return_code}")
                return False
            
        except Exception as e:
            logger.error(f"Ошибка воспроизведения видео: {e}")
            self.is_playing = False
            return False
    
    def stop_playback(self):
        """Остановить воспроизведение"""
        if self.current_process and self.is_playing:
            self.current_process.terminate()
            self.is_playing = False
            logger.info("Воспроизведение остановлено")

class RecordingGUI:
    """GUI для интерфейса записи"""
    
    def __init__(self):
        self.root = None
        self.recording_window = None
        self.timer_label = None
        self._gui_ready = threading.Event()
        
    def initialize_gui(self):
        """Инициализировать GUI в главном потоке"""
        self.root = tk.Tk()
        self.root.title("Recording Interface")
        self.root.withdraw()  # Скрываем по умолчанию
        self._gui_ready.set()
        
    def show_recording_interface(self, current_question, total_questions, hero_name):
        """Показать полноэкранный интерфейс записи аудио"""
        if not self._gui_ready.is_set():
            logger.warning("GUI еще не готов")
            return
            
        # Запускаем в главном потоке Tkinter
        if self.root:
            self.root.after(0, self._show_recording_interface, current_question, total_questions, hero_name)
    
    def _show_recording_interface(self, current_question, total_questions, hero_name):
        """Внутренний метод для показа интерфейса (вызывается в главном потоке)"""
        try:
            logger.info(f"Показываю интерфейс записи для {hero_name}")
            
            if self.recording_window and self.recording_window.winfo_exists():
                self.recording_window.lift()
                return
                
            self.recording_window = tk.Toplevel(self.root)
            self.recording_window.title("Запись аудио")
            
            # Полноэкранный режим
            self.recording_window.attributes('-fullscreen', True)
            self.recording_window.configure(bg='#1a1a1a')
            self.recording_window.attributes('-topmost', True)
            
            # Запрещаем закрытие окна
            self.recording_window.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # Создаем основной фрейм
            main_frame = tk.Frame(self.recording_window, bg='#1a1a1a')
            main_frame.pack(expand=True, fill='both')
            
            # Заголовок
            title_label = tk.Label(
                main_frame, 
                text="ЗАДАЙТЕ ВОПРОС ГЕРОЮ",
                font=('Arial', 36, 'bold'),
                fg='white',
                bg='#1a1a1a'
            )
            title_label.pack(pady=40)
            
            # Имя героя
            hero_label = tk.Label(
                main_frame,
                text=f"👤 {hero_name}",
                font=('Arial', 28),
                fg='#cccccc',
                bg='#1a1a1a'
            )
            hero_label.pack(pady=20)
            
            # Номер вопроса
            progress_label = tk.Label(
                main_frame,
                text=f"Вопрос {current_question} из {total_questions}",
                font=('Arial', 24),
                fg='#cccccc',
                bg='#1a1a1a'
            )
            progress_label.pack(pady=30)
            
            # Анимированный микрофон
            mic_label = tk.Label(
                main_frame,
                text="🎤",
                font=("Arial", 120),
                bg='#1a1a1a',
                fg='#ffffff'
            )
            mic_label.pack(pady=50)
            
            # Таймер обратного отсчета
            self.timer_label = tk.Label(
                main_frame,
                text="3",
                font=('Arial', 72, 'bold'),
                fg='#ff4444',
                bg='#1a1a1a'
            )
            self.timer_label.pack(pady=40)
            
            # Инструкция
            info_label = tk.Label(
                main_frame,
                text="ГОВОРИТЕ СЕЙЧАС...",
                font=('Arial', 20),
                fg='#888888',
                bg='#1a1a1a'
            )
            info_label.pack(pady=30)
            
            # Запускаем таймер
            self.start_recording_timer(3)
            
            # Обновляем окно
            self.recording_window.update()
            
            logger.info("Интерфейс записи отображен")
            
        except Exception as e:
            logger.error(f"Ошибка отображения интерфейса записи: {e}")

    def start_recording_timer(self, seconds):
        """Запустить таймер обратного отсчета"""
        if seconds >= 0:
            self.timer_label.config(text=str(seconds))
            # Меняем цвет при малом времени
            if seconds <= 5:
                self.timer_label.config(fg='#ff0000')
            self.recording_window.after(1000, self.start_recording_timer, seconds - 1)
        else:
            self.hide_recording_interface()

    def hide_recording_interface(self):
        """Скрыть интерфейс записи"""
        if self.recording_window:
            self.recording_window.destroy()
            self.recording_window = None
        logger.info("Интерфейс записи скрыт")
        
    def run(self):
        """Запустить главный цикл GUI"""
        try:
            self.initialize_gui()
            self.root.mainloop()
        except Exception as e:
            logger.error(f"Ошибка GUI: {e}")

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
        logger.info(f"Начинаю сессию для {self.hero_name} на языке {self.language}")
        
        for question_num in range(1, self.question_count + 1):
            logger.info(f"Вопрос {question_num}/{self.question_count} для {self.hero_name}")
            
            # Показываем интерфейс записи
            self.gui.show_recording_interface(question_num, self.question_count, self.hero_name)
            
            # Даем время для отображения GUI
            time.sleep(2)
            
            # Записываем аудио
            audio_file = self.audio_recorder.record_audio(duration=3)
            
            # Скрываем интерфейс записи
            self.gui.hide_recording_interface()
            
            if not audio_file:
                logger.error(f"Не удалось записать аудио для вопроса {question_num}")
                continue
            
            # Отправляем аудио на сервер и получаем видео для воспроизведения
            video_path = self.send_audio_to_server(audio_file, question_num)
            
            # Удаляем временный аудиофайл
            try:
                os.unlink(audio_file)
            except:
                pass
            
            if video_path:
                # Воспроизводим полученное видео
                success = self.video_player.play_video(video_path)
                
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
            else:
                logger.error(f"Не удалось получить видео для вопроса {question_num}")
                # Воспроизводим заглушку
                fallback_success = self.play_fallback_video()
                self.session_history.append({
                    'question_number': question_num,
                    'hero_name': self.hero_name,
                    'language': self.language,
                    'audio_sent': False,
                    'video_played': fallback_success,
                    'video_source': 'fallback',
                    'timestamp': datetime.now().isoformat()
                })
        
        logger.info(f"Сессия завершена для {self.hero_name}")
        return self.session_history
    
    def send_audio_to_server(self, audio_file_path, question_num):
        """Отправить аудиофайл на Django сервер и получить видео"""
        try:
            # URL для отправки аудио (из config.py)
            django_url = DJANGO_URL
            api_url = f"{django_url}/subcategory/{self.subcategory_id}/ask/"
            logger.info(f"Отправляю аудио на {api_url}")
            
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
                response = requests.post(
                    api_url,
                    files=files,
                    data=data,
                    timeout=60  # Увеличиваем таймаут для обработки видео
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Аудио успешно отправлено, ответ сервера: {result}")
                    
                    # Получаем путь к видео из ответа
                    video_path = result.get('video')
                    if video_path:
                        logger.info(f"Получен путь к видео: {video_path}")
                        return self.download_video_if_needed(video_path)
                    else:
                        logger.warning("Сервер не вернул путь к видео")
                        return None
                else:
                    logger.error(f"❌ Ошибка сервера: {response.status_code}, {response.text}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети при отправке аудио: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при отправке аудио: {e}")
            return None
    
    def download_video_if_needed(self, video_path):
        """Скачать видео если это URL, или вернуть локальный путь"""
        try:
            # Если это полный URL
            if video_path.startswith('http'):
                # Скачиваем видео во временный файл
                temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                temp_video_path = temp_video.name
                temp_video.close()
                
                logger.info(f"Скачиваю видео с {video_path}")
                response = requests.get(video_path, stream=True, timeout=60)
                
                if response.status_code == 200:
                    with open(temp_video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    logger.info(f"Видео скачано: {temp_video_path} ({os.path.getsize(temp_video_path)} байт)")
                    return temp_video_path
                else:
                    logger.error(f"Не удалось скачать видео: {response.status_code}")
                    return None
            
            # Если это относительный путь (начинается с /media/)
            elif video_path.startswith('/media/'):
                # Пробуем найти локально
                local_path = video_path.replace('/media/', 'media/')
                if os.path.exists(local_path):
                    return local_path
                else:
                    logger.error(f"Локальный файл не найден: {local_path}")
                    # Пробуем скачать с сервера
                    full_url = f"{DJANGO_URL}{video_path}"
                    return self.download_video_if_needed(full_url)
            
            # Если это просто имя файла или путь
            else:
                # Пробуем найти в разных местах
                possible_paths = [
                    f"media/hero_videos/{self.hero_name}/{video_path}",
                    f"media/{video_path}",
                    video_path
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        return path
                
                logger.error(f"Видео не найдено по путям: {possible_paths}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка обработки видео: {e}")
            return None
    
    def play_fallback_video(self):
        """Воспроизвести видео-заглушку при ошибке"""
        fallback_videos = [
            "media/greet_video.mp4",
            "media/end_video.mp4"
        ]
        
        for video_path in fallback_videos:
            if os.path.exists(video_path):
                logger.info(f"Воспроизвожу видео-заглушку: {video_path}")
                return self.video_player.play_video(video_path)
        
        # Если нет ни одного видео, просто ждем
        logger.warning("Видео-заглушки не найдены, ожидаем 5 секунд")
        time.sleep(5)
        return False

class PlaybackModule:
    """Основной модуль воспроизведения"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.gui = RecordingGUI()
        self.audio_recorder = AudioRecorder()
        self.video_player = VideoPlayer()
        self.full_history = []
        self.playback_active = False
        
    def start_playback(self, heroes_data: dict):
        """Начать полный процесс воспроизведения"""
        try:
            logger.info("Запускаю процесс воспроизведения")
            self.playback_active = True
            
            # Получаем данные
            heroes = heroes_data.get('hero_names', [])
            subcategory_id = heroes_data.get('subcategory_id')
            total_videos = heroes_data.get('total_videos', 0)
            
            logger.info(f"Обрабатываю {len(heroes)} героев: {heroes}")
            logger.info(f"ID подкатегории: {subcategory_id}, Всего видео: {total_videos}")
            
            # Проверяем видеофайлы
            self.check_video_files()
            
            # 1. Воспроизводим приветственное видео
            logger.info("Воспроизвожу приветственное видео...")
            self.play_greeting_video()
            
            # 2. Запускаем сессии для каждого героя
            for hero_name in heroes:
                if not self.playback_active:
                    logger.info("Воспроизведение остановлено")
                    break
                    
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
            
            # 3. Воспроизводим завершающее видео
            if self.playback_active:
                logger.info("Воспроизвожу завершающее видео...")
                self.play_ending_video()
            
            # 4. Публикуем событие завершения
            logger.info("Процесс воспроизведения успешно завершен")
            self.publish_playback_finished(heroes)
            
        except Exception as e:
            logger.error(f"Ошибка процесса воспроизведения: {e}")
            self.publish_playback_error(str(e))
        finally:
            self.playback_active = False
    
    def publish_playback_finished(self, heroes):
        """Публикация события завершения воспроизведения"""
        try:
            logger.info("Публикую событие playback_finished")
            self.event_bus.publish("playback_finished", {
                "heroes": heroes,
                "total_questions": len(heroes) * 6,
                "timestamp": time.time(),
                "message": "Воспроизведение завершено успешно"
            })
            logger.info("Событие playback_finished опубликовано")
        except Exception as e:
            logger.error(f"Ошибка публикации события playback_finished: {e}")
    
    def publish_playback_error(self, error_message):
        """Публикация события ошибки"""
        try:
            logger.info("Публикую событие playback_error")
            self.event_bus.publish("playback_error", {
                "error": error_message,
                "timestamp": time.time(),
                "message": "Ошибка воспроизведения"
            })
        except Exception as e:
            logger.error(f"Ошибка публикации события playback_error: {e}")
    
    def check_video_files(self):
        """Проверить существование видеофайлов"""
        greeting_path = "media/greet_video.mp4"
        ending_path = "media/end_video.mp4"
        
        if not os.path.exists(greeting_path):
            logger.warning(f"Приветственное видео не найдено: {greeting_path}")
        else:
            logger.info(f"Приветственное видео найдено: {greeting_path}")
            
        if not os.path.exists(ending_path):
            logger.warning(f"Завершающее видео не найдено: {ending_path}")
        else:
            logger.info(f"Завершающее видео найдено: {ending_path}")
    
    def play_greeting_video(self):
        """Воспроизвести приветственное видео"""
        greeting_path = "media/greet_video.mp4"
        logger.info(f"Воспроизвожу приветственное видео: {greeting_path}")
        
        if os.path.exists(greeting_path):
            success = self.video_player.play_video(greeting_path)
            if not success:
                logger.error("Не удалось воспроизвести приветственное видео")
            return success
        else:
            logger.error(f"Приветственное видео не найдено: {greeting_path}")
            # Имитируем задержку если видео нет
            time.sleep(5)
            return False
    
    def play_ending_video(self):
        """Воспроизвести завершающее видео"""
        ending_path = "media/end_video.mp4"
        logger.info(f"Воспроизвожу завершающее видео: {ending_path}")
        
        if os.path.exists(ending_path):
            success = self.video_player.play_video(ending_path)
            if not success:
                logger.error("Не удалось воспроизвести завершающее видео")
            return success
        else:
            logger.error(f"Завершающее видео не найдено: {ending_path}")
            # Имитируем задержку если видео нет
            time.sleep(5)
            return False
    
    def stop_playback(self):
        """Экстренная остановка воспроизведения"""
        logger.info("Экстренная остановка воспроизведения")
        self.playback_active = False
        self.audio_recorder.is_recording = False
        self.video_player.stop_playback()
        self.gui.hide_recording_interface()

def main():
    """Точка входа для запуска как отдельного процесса"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger.info(f"Использую Django URL: {DJANGO_URL}")
    
    # Создаем event bus для публикации событий
    event_bus = EventBus()
    
    # Получаем данные из аргументов командной строки
    if len(sys.argv) > 1:
        try:
            heroes_data = json.loads(sys.argv[1])
            logger.info(f"Получены данные героев: {heroes_data}")
            
            # Проверяем структуру данных
            if isinstance(heroes_data, list):
                # Если пришел список, преобразуем в словарь
                processed_data = {
                    'hero_names': heroes_data,
                    'subcategory_id': 13,
                    'total_videos': 0
                }
                logger.info("Преобразовано из списка в словарь")
            else:
                processed_data = heroes_data
                
            logger.info(f"Герои: {processed_data.get('hero_names', [])}")
            logger.info(f"ID подкатегории: {processed_data.get('subcategory_id')}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга данных героев: {e}")
            sys.exit(1)
    else:
        logger.error("Данные героев не предоставлены")
        sys.exit(1)
    
    # Создаем и запускаем модуль
    playback_module = PlaybackModule(event_bus)
    
    # Запускаем GUI в отдельном потоке
    gui_thread = threading.Thread(target=playback_module.gui.run, daemon=True)
    gui_thread.start()
    
    # Ждем инициализации GUI
    time.sleep(2)
    
    # Запускаем воспроизведение в отдельном потоке
    playback_thread = threading.Thread(
        target=playback_module.start_playback, 
        args=(processed_data,),
        daemon=True
    )
    playback_thread.start()
    
    # Запускаем обработку событий
    try:
        event_bus.start()
    except KeyboardInterrupt:
        logger.info("Модуль воспроизведения прерван")
        playback_module.stop_playback()
    finally:
        # Даем время для корректного завершения
        playback_thread.join(timeout=5.0)

if __name__ == "__main__":
    main()