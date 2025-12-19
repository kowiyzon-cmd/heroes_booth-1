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
from datetime import datetime
import tkinter as tk
from tkinter import ttk, font
import traceback
from pathlib import Path
import pyaudio
import wave


# ==========================
# НАСТРОЙКИ ЗАПИСИ АУДИО
# ==========================
RECORD_DURATION_SECONDS = 10  # ЕДИНСТВЕННЫЙ параметр для управления временем записи

# Добавляем путь к корневой директории для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_bus import EventBus
from config import BASE_URL, HERO_VIDEOS_DIR

# Настройка логирования ДО создания логгера
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playback_debug.log')

# Создаем логгер с выводом в консоль И файл
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Очищаем предыдущие обработчики
logger.handlers = []

# Форматтер
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Консольный обработчик
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Файловый обработчик
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Добавляем обработчики
logger.addHandler(console_handler)
logger.addHandler(file_handler)

logger.info("=" * 80)
logger.info("🚀 МОДУЛЬ ВОСПРОИЗВЕДЕНИЯ ЗАПУЩЕН (ОБНОВЛЕННАЯ ВЕРСИЯ)")
logger.info("=" * 80)
logger.info(f"📁 Логи будут записаны в: {log_file}")
logger.info(f"🌐 BASE_URL: {BASE_URL}")
logger.info(f"📁 Директория с видео: {HERO_VIDEOS_DIR}")
logger.info(f"📁 Текущая директория: {os.getcwd()}")
logger.info(f"⏱ Длительность записи аудио: {RECORD_DURATION_SECONDS} сек.")

class VideoManager:
    """Менеджер для работы с видеофайлами"""
    
    @staticmethod
    def get_video_path(hero_name, record_id):
        """Получить путь к локальному видеофайлу"""
        # Формируем имя файла по шаблону: hero_name_record_id.mp4
        video_filename = f"{hero_name}_{record_id}.mp4"
        video_path = os.path.join(HERO_VIDEOS_DIR, hero_name, video_filename)
        
        logger.debug(f"Ищу видео: {video_path}")
        
        if os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            logger.info(f"✅ Видео найдено: {video_path} ({file_size} байт)")
            return video_path
        else:
            # Пробуем альтернативные варианты именования
            alternative_paths = [
                os.path.join(HERO_VIDEOS_DIR, hero_name, f"{record_id}.mp4"),
                os.path.join(HERO_VIDEOS_DIR, hero_name, f"question_{record_id}.mp4"),
                os.path.join(HERO_VIDEOS_DIR, hero_name, f"{hero_name}_{record_id}.mp4".replace(" ", "_")),
            ]
            
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    file_size = os.path.getsize(alt_path)
                    logger.info(f"✅ Видео найдено (альтернативный путь): {alt_path} ({file_size} байт)")
                    return alt_path
            
            logger.error(f"❌ Видео не найдено: {video_path}")
            logger.error("Доступные видео в директории:")
            hero_dir = os.path.join(HERO_VIDEOS_DIR, hero_name)
            if os.path.exists(hero_dir):
                for file in os.listdir(hero_dir):
                    if file.endswith('.mp4'):
                        logger.error(f"  - {file}")
            
            return None
    
    @staticmethod
    def check_prerecorded_videos(heroes):
        """Проверить наличие предзаписанных видео для героев"""
        logger.info("🔍 Проверяю наличие предзаписанных видео...")
        
        missing_videos = []
        
        for hero in heroes[::-1]:
            hero_dir = os.path.join(HERO_VIDEOS_DIR, hero)
            
            if not os.path.exists(hero_dir):
                logger.warning(f"⚠️ Директория для героя {hero} не найдена: {hero_dir}")
                missing_videos.append(hero)
                continue
            
            # Ожидаем 6 видео на героя (номера 1-6)
            expected_count = 6
            actual_count = 0
            
            for i in range(1, expected_count + 1):
                video_path = VideoManager.get_video_path(hero, i)
                if video_path:
                    actual_count += 1
                else:
                    logger.warning(f"⚠️ Не найдено видео для {hero}, вопрос {i}")
            
            if actual_count < expected_count:
                missing_videos.append(f"{hero} ({actual_count}/{expected_count})")
            
            logger.info(f"✅ Герой {hero}: найдено {actual_count}/{expected_count} видео")
        
        if missing_videos:
            logger.warning(f"⚠️ Пропущенные видео: {missing_videos}")
        else:
            logger.info("🎉 Все видео найдены!")
        
        return len(missing_videos) == 0

class SimpleAudioRecorder:
    """Класс для реальной записи аудио с микрофона"""

    def __init__(self, gui_callback=None):
        self.sample_rate = 16000  # Начальное значение
        self.channels = 1
        self.format = pyaudio.paInt16
        self.chunk = 1024
        self.gui_callback = gui_callback
        self.stop_recording = False
        self.audio = None
        self.stream = None

    def find_supported_sample_rate(self, audio):
        """Найти поддерживаемую частоту дискретизации"""
        try:
            device_info = audio.get_default_input_device_info()
            logger.info(f"📊 Устройство записи: {device_info.get('name')}")
            logger.info(f"📊 Частота по умолчанию: {device_info.get('defaultSampleRate')}")
            
            # Пробуем разные частоты дискретизации
            sample_rates = [16000, 44100, 48000, 22050, 8000, 96000, 11025]
            
            for rate in sample_rates:
                try:
                    # Пробуем открыть поток с этой частотой
                    test_stream = audio.open(
                        format=self.format,
                        channels=self.channels,
                        rate=rate,
                        input=True,
                        frames_per_buffer=self.chunk,
                        input_device_index=device_info['index']
                    )
                    test_stream.close()
                    logger.info(f"✅ Частота {rate} Hz поддерживается")
                    return rate
                except Exception as e:
                    logger.debug(f"⚠️ Частота {rate} Hz не поддерживается: {str(e)[:50]}")
            
            # Если ничего не подошло, пробуем частоту по умолчанию
            default_rate = int(device_info.get('defaultSampleRate', 44100))
            logger.warning(f"⚠️ Ни одна частота не подошла, пробую частоту по умолчанию: {default_rate} Hz")
            return default_rate
            
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске частоты дискретизации: {e}")
            return 44100  # Возвращаем безопасное значение

    def record_audio(self, duration=RECORD_DURATION_SECONDS):
        """Записать аудио с микрофона и вернуть путь к WAV файлу"""
        self.audio = pyaudio.PyAudio()
        self.stream = None
        frames = []

        try:
            logger.info(f"🎤 Начинаю ЗАПИСЬ с микрофона ({duration} сек)...")
            
            # Находим поддерживаемую частоту дискретизации
            self.sample_rate = self.find_supported_sample_rate(self.audio)
            logger.info(f"📊 Использую частоту дискретизации: {self.sample_rate} Hz")
            
            device_info = self.audio.get_default_input_device_info()
            
            # Открываем поток с найденной частотой
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk,
                input_device_index=device_info['index']
            )
            
            total_chunks = int(self.sample_rate / self.chunk * duration)
            self.stop_recording = False
            
            logger.info(f"📊 Всего чанков для записи: {total_chunks}")

            for i in range(total_chunks):
                if self.stop_recording:
                    logger.info("🛑 Запись остановлена досрочно")
                    break
                    
                try:
                    # Читаем данные из потока
                    data = self.stream.read(self.chunk, exception_on_overflow=False)
                    frames.append(data)
                    
                    # Обновляем GUI каждую секунду
                    if self.gui_callback and i % (self.sample_rate // self.chunk) == 0:
                        elapsed_seconds = i * self.chunk / self.sample_rate
                        seconds_left = int(duration - elapsed_seconds)
                        self.gui_callback(seconds_left)
                        
                except IOError as e:
                    logger.warning(f"⚠️ Ошибка чтения аудио-чанка {i}: {e}")
                    # Добавляем тишину вместо потерянных данных
                    frames.append(b'\x00' * self.chunk * 2)

            logger.info(f"✅ Запись завершена, собрано {len(frames)} чанков")

            # Создаём временный WAV файл
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name

            # Сохраняем аудио в WAV файл
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b"".join(frames))

            file_size = os.path.getsize(wav_path)
            logger.info(f"💾 WAV файл сохранён: {wav_path} ({file_size} байт)")
            
            # Проверяем, не пустой ли файл
            if file_size < 100:  # Минимальный размер для WAV заголовка
                logger.warning("⚠️ Создан очень маленький WAV файл. Возможно, запись не удалась.")
                # Создаем тестовый аудиофайл с тишиной
                self.create_silent_wav(wav_path, duration)
                file_size = os.path.getsize(wav_path)
                logger.info(f"📁 Создан тестовый WAV файл: {wav_path} ({file_size} байт)")

            return wav_path

        except Exception as e:
            logger.error(f"❌ Критическая ошибка записи аудио: {e}")
            logger.error(traceback.format_exc())
            
            # Пробуем создать пустой аудиофайл для продолжения работы
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    wav_path = tmp.name
                
                self.create_silent_wav(wav_path, duration)
                logger.warning(f"⚠️ Создан тестовый WAV файл после ошибки: {wav_path}")
                return wav_path
            except Exception as inner_e:
                logger.error(f"❌ Не удалось создать тестовый файл: {inner_e}")
                return None

        finally:
            self.cleanup()

    def create_silent_wav(self, filepath, duration):
        """Создать WAV файл с тишиной (для тестирования)"""
        try:
            sample_rate = self.sample_rate if hasattr(self, 'sample_rate') else 16000
            num_frames = int(sample_rate * duration)
            silent_data = b'\x00' * num_frames * 2  # 2 байта на сэмпл для paInt16
            
            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 2 байта для paInt16
                wf.setframerate(sample_rate)
                wf.writeframes(silent_data)
                
            logger.info(f"📁 Создан WAV с тишиной: {filepath}, {duration} сек, {sample_rate} Hz")
        except Exception as e:
            logger.error(f"❌ Ошибка создания тестового WAV: {e}")

    def cleanup(self):
        """Очистка ресурсов"""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
        except Exception as e:
            logger.debug(f"⚠️ Ошибка при закрытии потока: {e}")
        
        try:
            if self.audio:
                self.audio.terminate()
                self.audio = None
        except Exception as e:
            logger.debug(f"⚠️ Ошибка при завершении PyAudio: {e}")

    def stop(self):
        """Остановить запись досрочно"""
        self.stop_recording = True
        self.cleanup()
    
    def __del__(self):
        """Деструктор для гарантированной очистки"""
        self.cleanup()

class VideoPlayer:
    """Класс для воспроизведения видео"""
    
    def play_video(self, video_path, blocking=True):
        """Воспроизвести видеофайл"""
        try:
            logger.info(f"🎬 Пытаюсь воспроизвести видео: {video_path}")
            
            # Проверяем существование файла
            if not os.path.exists(video_path):
                logger.error(f"❌ Видеофайл не найден: {video_path}")
                return False
            
            file_size = os.path.getsize(video_path)
            logger.info(f"✅ Видеофайл найден: {video_path} ({file_size} байт)")
            
            # Используем mpv
            cmd = ["mpv", "--fs", "--no-input-default-bindings", video_path]
            logger.info(f"🚀 Запускаю команду: {' '.join(cmd)}")
            
            if blocking:
                # Запускаем с таймаутом
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    
                    if result.returncode == 0:
                        logger.info("✅ Видео воспроизведено успешно")
                        return True
                    else:
                        logger.warning(f"⚠️ mpv завершился с кодом: {result.returncode}")
                        if result.stderr:
                            logger.error(f"Ошибка mpv: {result.stderr[:200]}")
                        return True  # Все равно считаем успехом
                        
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️ Таймаут воспроизведения (120 секунд)")
                    return True
            else:
                # Неблокирующий запуск
                subprocess.Popen(cmd)
                logger.info("🎬 Видео запущено в фоновом режиме")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка воспроизведения видео: {e}")
            logger.error(traceback.format_exc())
            return False

class MainGUI:
    """Основной GUI приложения"""
    
    def __init__(self):
        self.root = None
        self.current_window = None
        self._initialized = False
        self.status_label = None
        self.progress_label = None
        self.timer_label = None
        self.is_recording = False
        self.recording_seconds_left = RECORD_DURATION_SECONDS
        
    def initialize(self):
        """Инициализировать GUI"""
        try:
            if not self._initialized:
                logger.info("🖥 Инициализирую Tkinter...")
                self.root = tk.Tk()
                self.root.title("AI Герои")
                self.root.configure(bg='#1a1a1a')
                
                # Скрываем корневое окно, будем использовать полноэкранные окна
                self.root.withdraw()
                
                self._initialized = True
                logger.info("✅ Tkinter инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Tkinter: {e}")
            logger.error(traceback.format_exc())
    
    def show_loading_screen(self, message="Загрузка..."):
        """Показать экран загрузки"""
        try:
            if not self._initialized:
                self.initialize()
            
            # Закрываем предыдущее окно
            if self.current_window:
                try:
                    self.current_window.destroy()
                except:
                    pass
            
            # Создаем новое окно
            self.current_window = tk.Toplevel(self.root)
            self.current_window.title("Загрузка")
            self.current_window.attributes('-fullscreen', True)
            self.current_window.configure(bg='#1a1a1a')
            
            # Центрируем содержимое
            main_frame = tk.Frame(self.current_window, bg='#1a1a1a')
            main_frame.pack(expand=True)
            
            # Индикатор загрузки
            loading_label = tk.Label(
                main_frame,
                text="⏳",
                font=('Arial', 72),
                bg='#1a1a1a',
                fg='#ffffff'
            )
            loading_label.pack(pady=30)
            
            # Сообщение
            message_label = tk.Label(
                main_frame,
                text=message,
                font=('Arial', 24),
                bg='#1a1a1a',
                fg='#cccccc'
            )
            message_label.pack(pady=20)
            
            # Обновляем окно
            self.current_window.update()
            logger.info(f"🖥 Показан экран загрузки: {message}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа экрана загрузки: {e}")
    
    def show_recording_screen(self, hero_name, question_num, total_questions):
        """Показать экран записи"""
        try:
            if not self._initialized:
                self.initialize()
            
            # Обновляем существующее окно или создаем новое
            if not self.current_window:
                self.current_window = tk.Toplevel(self.root)
                self.current_window.title("Запись вопроса")
                self.current_window.attributes('-fullscreen', True)
                self.current_window.configure(bg='#1a1a1a')
            
            # Очищаем окно
            for widget in self.current_window.winfo_children():
                widget.destroy()
            
            # Основной фрейм
            main_frame = tk.Frame(self.current_window, bg='#1a1a1a')
            main_frame.pack(expand=True, fill='both', padx=50, pady=50)
            
            # Верхняя панель с информацией
            top_frame = tk.Frame(main_frame, bg='#1a1a1a')
            top_frame.pack(fill='x', pady=(0, 50))
            
            # Имя героя
            hero_label = tk.Label(
                top_frame,
                text=f"👤 {hero_name}",
                font=('Arial', 28, 'bold'),
                bg='#1a1a1a',
                fg='#ffffff',
                anchor='w'
            )
            hero_label.pack(side='left', padx=(0, 50))
            
            # Прогресс
            progress_label = tk.Label(
                top_frame,
                text=f"Вопрос {question_num} из {total_questions}",
                font=('Arial', 24),
                bg='#1a1a1a',
                fg='#cccccc',
                anchor='e'
            )
            progress_label.pack(side='right')
            
            # Центральная область
            center_frame = tk.Frame(main_frame, bg='#1a1a1a')
            center_frame.pack(expand=True)
            
            # Главный заголовок
            title_label = tk.Label(
                center_frame,
                text="ЗАДАЙТЕ ВОПРОС ГЕРОЮ",
                font=('Arial', 36, 'bold'),
                bg='#1a1a1a',
                fg='#ffffff'
            )
            title_label.pack(pady=(0, 40))
            
            # Микрофон
            mic_label = tk.Label(
                center_frame,
                text="🎤",
                font=('Arial', 120),
                bg='#1a1a1a',
                fg='#ffffff'
            )
            mic_label.pack(pady=30)
            
            # Таймер
            self.timer_label = tk.Label(
                center_frame,
                text=str(RECORD_DURATION_SECONDS),
                font=('Arial', 72, 'bold'),
                bg='#1a1a1a',
                fg='#ff4444'
            )
            self.timer_label.pack(pady=30)
            
            # Время записи
            duration_label = tk.Label(
                center_frame,
                text=f"Время записи: {RECORD_DURATION_SECONDS} сек.",
                font=('Arial', 16),
                bg='#1a1a1a',
                fg='#888888'
            )
            duration_label.pack(pady=(0, 10))
            
            # Инструкция
            instruction_label = tk.Label(
                center_frame,
                text="ГОТОВЬТЕСЬ К ЗАПИСИ...",
                font=('Arial', 20),
                bg='#1a1a1a',
                fg='#888888'
            )
            instruction_label.pack(pady=20)
            
            # Нижняя панель
            bottom_frame = tk.Frame(main_frame, bg='#1a1a1a')
            bottom_frame.pack(fill='x', pady=(50, 0))
            
            # Статус
            self.status_label = tk.Label(
                bottom_frame,
                text="⏳ Подготовка к записи...",
                font=('Arial', 18),
                bg='#1a1a1a',
                fg='#aaaaaa'
            )
            self.status_label.pack()
            
            # Обновляем окно
            self.current_window.update()
            self.is_recording = False
            self.recording_seconds_left = RECORD_DURATION_SECONDS
            
            logger.info(f"🖥 Показан экран записи для {hero_name}, вопрос {question_num}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа экрана записи: {e}")
            logger.error(traceback.format_exc())
    
    def show_waiting_screen(self, hero_name, message="Обработка ответа..."):
        """Показать экран ожидания"""
        try:
            if not self._initialized:
                self.initialize()
            
            # Обновляем существующее окно
            if self.current_window:
                for widget in self.current_window.winfo_children():
                    widget.destroy()
                
                # Основной фрейм
                main_frame = tk.Frame(self.current_window, bg='#1a1a1a')
                main_frame.pack(expand=True, fill='both')
                
                # Анимация загрузки
                loading_label = tk.Label(
                    main_frame,
                    text="⏳",
                    font=('Arial', 72),
                    bg='#1a1a1a',
                    fg='#ffffff'
                )
                loading_label.pack(pady=50)
                
                # Сообщение
                message_label = tk.Label(
                    main_frame,
                    text=message,
                    font=('Arial', 24),
                    bg='#1a1a1a',
                    fg='#cccccc'
                )
                message_label.pack(pady=20)
                
                # Дополнительная информация
                info_label = tk.Label(
                    main_frame,
                    text=f"Герой: {hero_name}",
                    font=('Arial', 18),
                    bg='#1a1a1a',
                    fg='#888888'
                )
                info_label.pack(pady=10)
                
                # Обновляем окно
                self.current_window.update()
                self.is_recording = False
                logger.info(f"🖥 Показан экран ожидания: {message}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка показа экрана ожидания: {e}")
    
    def start_recording_mode(self):
        """Переключить интерфейс в режим записи"""
        try:
            if self.status_label:
                self.status_label.config(text="🎤 ИДЁТ ЗАПИСЬ... ГОВОРИТЕ СЕЙЧАС!", fg='#44ff44')
            
            if self.timer_label:
                # Обновляем таймер с начальным значением
                self.update_recording_timer(RECORD_DURATION_SECONDS)
            
            self.is_recording = True
            self.recording_seconds_left = RECORD_DURATION_SECONDS
            
            if self.current_window:
                self.current_window.update()
                
        except Exception as e:
            logger.error(f"❌ Ошибка перехода в режим записи: {e}")
    
    def update_recording_timer(self, seconds_left):
        """Обновить таймер записи"""
        try:
            if self.timer_label:
                self.recording_seconds_left = seconds_left
                
                # Обновляем отображаемое значение
                display_seconds = max(0, seconds_left)
                self.timer_label.config(text=str(display_seconds))
                
                # Изменяем цвет в зависимости от оставшегося времени
                if display_seconds > RECORD_DURATION_SECONDS * 0.5:
                    self.timer_label.config(fg='#44ff44')  # Зеленый для первой половины
                elif display_seconds > 3:
                    self.timer_label.config(fg='#ffff44')  # Желтый для середины
                elif display_seconds > 0:
                    self.timer_label.config(fg='#ff4444')  # Красный для конца
                else:
                    self.timer_label.config(text="✓", fg='#44ff44')
                    if self.status_label:
                        self.status_label.config(text="✅ Запись завершена", fg='#44ff44')
                
                # Обновляем интерфейс
                if self.current_window:
                    self.current_window.update_idletasks()
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обновления таймера: {e}")
    
    def close(self):
        """Закрыть все окна"""
        try:
            if self.current_window:
                self.current_window.destroy()
            if self.root:
                self.root.quit()
        except:
            pass
    
    def run(self):
        """Запустить главный цикл GUI"""
        try:
            if not self._initialized:
                self.initialize()
            
            if self._initialized:
                logger.info("🖥 Запускаю главный цикл Tkinter...")
                # Запускаем в режиме обновления без блокировки
                self.root.after(100, self._update_loop)
                self.root.mainloop()
                
        except Exception as e:
            logger.error(f"❌ Ошибка GUI цикла: {e}")
            logger.error(traceback.format_exc())
    
    def _update_loop(self):
        """Цикл обновления GUI"""
        try:
            self.root.update_idletasks()
            self.root.update()
            self.root.after(100, self._update_loop)
        except:
            pass

def play_transition_video(gui, video_path, message="Переход..."):
    """Воспроизвести переходное видео с сохранением GUI"""
    try:
        logger.info(f"🎬 Начинаю переход: {video_path}")
        
        # Показываем экран загрузки
        gui.show_waiting_screen("", message)
        time.sleep(1)
        
        # Воспроизводим видео
        video_player = VideoPlayer()
        if os.path.exists(video_path):
            video_player.play_video(video_path)
        else:
            logger.warning(f"⚠️ Видео перехода не найдено: {video_path}")
            time.sleep(3)
        
        logger.info(f"✅ Переход завершен: {video_path}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка воспроизведения переходного видео: {e}")

def record_audio_with_sync(gui, audio_recorder, hero_name, question_num):
    """Синхронизированная запись аудио с обновлением GUI"""
    try:
        logger.info(f"🎤 Запись аудио для {hero_name}, вопрос {question_num}")
        
        # Показываем короткий обратный отсчет перед началом записи (3 секунды)
        gui.show_recording_screen(hero_name, question_num, 6)
        
        # Короткая подготовка (3 секунды)
        for sec in range(3, 0, -1):
            if gui.timer_label:
                gui.timer_label.config(text=str(sec), fg='#ffff44')
                if sec == 1:
                    if gui.status_label:
                        gui.status_label.config(text="🎤 НАЧАЛО ЗАПИСИ ЧЕРЕЗ...", fg='#ffff44')
            if gui.current_window:
                gui.current_window.update()
            time.sleep(1)
        
        # Переключаем в режим записи
        gui.start_recording_mode()
        
        # Начинаем запись в отдельном потоке
        audio_file = None
        recording_complete = threading.Event()
        
        def record_thread():
            nonlocal audio_file
            try:
                # Начинаем запись с callback для обновления GUI
                audio_file = audio_recorder.record_audio(duration=RECORD_DURATION_SECONDS)
            except Exception as e:
                logger.error(f"❌ Ошибка в потоке записи: {e}")
            finally:
                recording_complete.set()
        
        # Запускаем поток записи
        record_thread_obj = threading.Thread(target=record_thread, daemon=True)
        record_thread_obj.start()
        
        # Ждем завершения записи
        recording_complete.wait(timeout=RECORD_DURATION_SECONDS + 5)
        
        # Завершаем
        audio_recorder.stop()
        
        # Финальное обновление GUI
        if gui.timer_label:
            gui.timer_label.config(text="✓", fg='#44ff44')
        if gui.status_label:
            gui.status_label.config(text="✅ Запись завершена", fg='#44ff44')
        if gui.current_window:
            gui.current_window.update()
        
        time.sleep(1)  # Короткая пауза перед переходом
        
        return audio_file
        
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизированной записи: {e}")
        logger.error(traceback.format_exc())
        return None

def main():
    """Главная функция"""
    gui = None
    audio_recorder = None
    
    try:
        # Получаем данные из аргументов
        logger.info(f"📦 Получаю данные из аргументов...")
        
        if len(sys.argv) > 1:
            try:
                raw_data = sys.argv[1]
                logger.info(f"Сырые данные: {raw_data[:100]}...")
                
                data = json.loads(raw_data)
                logger.info("✅ JSON успешно распарсен")
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга JSON: {e}")
                data = {'hero_names': ['Test_Hero'], 'subcategory_id': 13}
        else:
            logger.warning("⚠️ Данные не предоставлены в аргументах")
            data = {'hero_names': ['Test_Hero'], 'subcategory_id': 13}
        
        heroes = data.get('hero_names', [])
        subcategory_id = data.get('subcategory_id', 13)
        
        logger.info(f"🎭 Герои для обработки: {heroes}")
        logger.info(f"🔢 ID подкатегории: {subcategory_id}")
        
        # Проверяем наличие видео
        all_videos_available = VideoManager.check_prerecorded_videos(heroes)
        
        if not all_videos_available:
            logger.warning("⚠️ Некоторые видео отсутствуют, но продолжаю работу...")
        
        # Создаем компоненты
        logger.info("🛠 Создаю компоненты...")
        gui = MainGUI()
        
        # Создаем аудиорекордер с callback для обновления GUI
        def update_timer_callback(seconds_left):
            """Callback для обновления таймера из аудиорекордера"""
            if gui.root:
                gui.root.after(0, gui.update_recording_timer, seconds_left)
        
        audio_recorder = SimpleAudioRecorder(gui_callback=update_timer_callback)
        video_player = VideoPlayer()
        
        # Запускаем GUI в отдельном потоке
        logger.info("🖥 Запускаю GUI в отдельном потоке...")
        gui_thread = threading.Thread(target=gui.run, daemon=True)
        gui_thread.start()
        
        # Даем время на инициализацию GUI
        logger.info("⏳ Ожидаю инициализацию GUI (3 секунды)...")
        time.sleep(3)
        
        # 1. Приветственное видео
        logger.info("🎬 ШАГ 1: ПРИВЕТСТВЕННОЕ ВИДЕО")
        play_transition_video(gui, "media/greet_video.mp4", "Начало сессии...")
        
        # 2. Сессии героев
        logger.info("🎬 ШАГ 2: СЕССИИ ГЕРОЕВ")
        for hero_idx, hero in enumerate(heroes, 1):
            logger.info(f"\n🎭 [{hero_idx}/{len(heroes)}] НАЧИНАЮ СЕССИЮ ДЛЯ: {hero}")
            
            # Показываем экран загрузки для героя
            gui.show_loading_screen(f"Подготовка к сессии с {hero}...")
            time.sleep(2)
            
            for question_num in range(1, 7):  # 6 вопросов
                logger.info(f"❓ ВОПРОС {question_num}/6 ДЛЯ {hero}")
                
                # Синхронизированная запись аудио
                audio_file = record_audio_with_sync(gui, audio_recorder, hero, question_num)
                
                if not audio_file:
                    logger.error("❌ Не удалось записать аудио")
                    gui.show_waiting_screen(hero, "Ошибка записи аудио")
                    time.sleep(3)
                    continue
                
                # Показываем экран ожидания
                gui.show_waiting_screen(hero, "Отправка вопроса на сервер...")
                
                # Отправляем на сервер
                logger.info(f"📤 Отправляю аудио на сервер...")
                try:
                    api_url = f"{BASE_URL}/api/sub/{subcategory_id}/ask/"
                    logger.info(f"🌐 URL сервера: {api_url}")
                    
                    with open(audio_file, 'rb') as f:
                        files = {'audio': (f'audio.wav', f, 'audio/wav')}
                        data = {'hero_name': hero, 'language': 'ru'}
                        
                        response = requests.post(api_url, files=files, data=data, timeout=30)
                        logger.info(f"📥 Ответ сервера: статус {response.status_code}")
                        
                        if response.status_code == 200:
                            result = response.json().get("fastapi_data", {})
                            logger.info(f"✅ Сервер успешно принял аудио: {result}")
                            
                            # Получаем record_id и hero_name из ответа
                            record_id = result.get('record_id')
                            server_hero_name = result.get('hero_name')
                            
                            if record_id and server_hero_name:
                                logger.info(f"📊 Получены данные: hero={server_hero_name}, record_id={record_id}")
                                
                                # Ищем локальное видео
                                local_video_path = VideoManager.get_video_path(server_hero_name, record_id)
                                
                                if local_video_path:
                                    # Показываем экран ожидания перед воспроизведением
                                    gui.show_waiting_screen(server_hero_name, "Подготовка ответа героя...")
                                    time.sleep(2)
                                    
                                    # Воспроизводим видео
                                    logger.info(f"🎬 Воспроизвожу видео: {local_video_path}")
                                    video_player.play_video(local_video_path)
                                    
                                    # Показываем экран ожидания после видео
                                    gui.show_waiting_screen(server_hero_name, "Подготовка к следующему вопросу...")
                                    time.sleep(2)
                                else:
                                    logger.error("❌ Не удалось найти видео для воспроизведения")
                                    gui.show_waiting_screen(server_hero_name, "Ошибка: видео не найдено")
                                    time.sleep(3)
                            else:
                                logger.error("❌ В ответе сервера отсутствуют record_id или hero_name")
                                gui.show_waiting_screen(hero, "Ошибка: неверный ответ сервера")
                                time.sleep(3)
                        else:
                            logger.error(f"❌ Ошибка сервера: {response.status_code}")
                            if response.text:
                                logger.error(f"Тело ответа: {response.text[:200]}")
                            gui.show_waiting_screen(hero, "Ошибка сервера")
                            time.sleep(3)
                            
                except requests.exceptions.RequestException as e:
                    logger.error(f"❌ Ошибка сети: {e}")
                    gui.show_waiting_screen(hero, "Ошибка сети")
                    time.sleep(3)
                except Exception as e:
                    logger.error(f"❌ Неожиданная ошибка: {e}")
                    logger.error(traceback.format_exc())
                    gui.show_waiting_screen(hero, "Ошибка обработки")
                    time.sleep(3)
                finally:
                    # Удаляем аудиофайл
                    try:
                        if audio_file and os.path.exists(audio_file):
                            os.unlink(audio_file)
                    except:
                        pass
            
            logger.info(f"✅ [{hero_idx}/{len(heroes)}] СЕССИЯ ЗАВЕРШЕНА: {hero}")
            
            # Переход между героями (если не последний)
            if hero_idx < len(heroes):
                gui.show_loading_screen(f"Переход к следующему герою...")
                time.sleep(2)
        
        # 3. Завершающее видео
        logger.info("\n🎬 ШАГ 3: ЗАВЕРШАЮЩЕЕ ВИДЕО")
        play_transition_video(gui, "media/end_video.mp4", "Завершение сессии...")
        
        # Финальный экран
        gui.show_loading_screen("🎉 Сессия завершена!")
        time.sleep(3)
        
        logger.info("\n✅ ВОСПРОИЗВЕДЕНИЕ УСПЕШНО ЗАВЕРШЕНО")
        
        # Публикуем событие завершения
        try:
            logger.info("📤 Публикую событие playback_finished...")
            event_bus = EventBus()
            event_bus.publish("playback_finished", {
                "heroes": heroes,
                "timestamp": time.time(),
                "message": "Воспроизведение завершено успешно"
            })
        except Exception as e:
            logger.error(f"❌ Ошибка отправки события: {e}")
            
    except KeyboardInterrupt:
        logger.info("\n🛑 ПРЕРВАНО ПОЛЬЗОВАТЕЛЕМ")
    except Exception as e:
        logger.error(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Закрываем GUI
        if gui:
            try:
                gui.close()
            except:
                pass
    
    logger.info("\n🏁 МОДУЛЬ ВОСПРОИЗВЕДЕНИЯ ЗАВЕРШИЛ РАБОТУ")

if __name__ == "__main__":
    main()
