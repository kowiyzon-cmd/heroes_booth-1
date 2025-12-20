#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест микрофона для Raspberry Pi
Записывает 5 секунд аудио и сохраняет в WAV файл
"""

import pyaudio
import wave
import os
import sys
from datetime import datetime

# Конфигурация
RECORD_DURATION = 5  # секунд
SAMPLE_RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024

def print_separator():
    print("=" * 60)

def list_audio_devices(audio):
    """Вывести список всех доступных аудио устройств"""
    print_separator()
    print("📋 ДОСТУПНЫЕ АУДИО УСТРОЙСТВА:")
    print_separator()
    
    device_count = audio.get_device_count()
    print(f"Всего устройств: {device_count}\n")
    
    for i in range(device_count):
        info = audio.get_device_info_by_index(i)
        print(f"Устройство #{i}:")
        print(f"  Название: {info['name']}")
        print(f"  Входов: {info['maxInputChannels']}")
        print(f"  Выходов: {info['maxOutputChannels']}")
        print(f"  Частота по умолчанию: {info['defaultSampleRate']} Hz")
        print()

def get_default_input_device(audio):
    """Получить информацию об устройстве ввода по умолчанию"""
    try:
        device_info = audio.get_default_input_device_info()
        print_separator()
        print("🎤 УСТРОЙСТВО ВВОДА ПО УМОЛЧАНИЮ:")
        print_separator()
        print(f"Название: {device_info['name']}")
        print(f"Индекс: {device_info['index']}")
        print(f"Входов: {device_info['maxInputChannels']}")
        print(f"Частота по умолчанию: {device_info['defaultSampleRate']} Hz")
        print_separator()
        return device_info
    except Exception as e:
        print(f"❌ Ошибка получения устройства ввода: {e}")
        return None

def test_sample_rates(audio, device_info):
    """Протестировать различные частоты дискретизации"""
    print_separator()
    print("🔍 ТЕСТИРОВАНИЕ ЧАСТОТ ДИСКРЕТИЗАЦИИ:")
    print_separator()
    
    sample_rates = [8000, 11025, 16000, 22050, 44100, 48000, 96000]
    supported_rates = []
    
    for rate in sample_rates:
        try:
            test_stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=rate,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=device_info['index']
            )
            test_stream.close()
            print(f"✅ {rate} Hz - ПОДДЕРЖИВАЕТСЯ")
            supported_rates.append(rate)
        except Exception as e:
            print(f"❌ {rate} Hz - НЕ ПОДДЕРЖИВАЕТСЯ ({str(e)[:40]}...)")
    
    print_separator()
    return supported_rates

def record_test_audio(audio, device_info, sample_rate):
    """Записать тестовое аудио"""
    print_separator()
    print(f"🎙️ НАЧИНАЮ ЗАПИСЬ ({RECORD_DURATION} секунд)...")
    print(f"Частота дискретизации: {sample_rate} Hz")
    print(f"Каналы: {CHANNELS}")
    print(f"Формат: paInt16")
    print_separator()
    
    frames = []
    
    try:
        # Открываем поток
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=sample_rate,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=device_info['index']
        )
        
        total_chunks = int(sample_rate / CHUNK * RECORD_DURATION)
        
        print(f"Запись... (всего чанков: {total_chunks})")
        
        for i in range(total_chunks):
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                # Показываем прогресс каждую секунду
                if i % (sample_rate // CHUNK) == 0:
                    seconds = i * CHUNK // sample_rate + 1
                    print(f"  Секунда {seconds}/{RECORD_DURATION}... ({len(frames)} чанков)")
                    
            except IOError as e:
                print(f"⚠️ Ошибка чтения чанка {i}: {e}")
                frames.append(b'\x00' * CHUNK * 2)
        
        # Закрываем поток
        stream.stop_stream()
        stream.close()
        
        print(f"✅ Запись завершена! Собрано {len(frames)} чанков")
        
        # Проверяем данные
        combined_data = b"".join(frames)
        total_size = len(combined_data)
        zero_count = combined_data.count(b'\x00')
        
        print(f"📊 Размер данных: {total_size} байт")
        print(f"📊 Нулевых байт: {zero_count} ({zero_count/total_size*100:.1f}%)")
        
        if zero_count == total_size:
            print("⚠️ ВНИМАНИЕ: Записана только тишина (все нули)!")
        elif zero_count > total_size * 0.95:
            print("⚠️ ВНИМАНИЕ: Почти вся запись - тишина!")
        else:
            print("✅ Данные выглядят нормально")
        
        return frames, sample_rate
        
    except Exception as e:
        print(f"❌ Ошибка записи: {e}")
        import traceback
        traceback.print_exc()
        return None, sample_rate

def save_wav_file(frames, sample_rate):
    """Сохранить WAV файл"""
    if not frames:
        print("❌ Нет данных для сохранения")
        return None
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_recording_{timestamp}.wav"
        
        print_separator()
        print(f"💾 СОХРАНЕНИЕ В ФАЙЛ: {filename}")
        print_separator()
        
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 2 байта для paInt16
            wf.setframerate(sample_rate)
            wf.writeframes(b"".join(frames))
        
        file_size = os.path.getsize(filename)
        print(f"✅ Файл сохранён: {filename}")
        print(f"📦 Размер файла: {file_size} байт ({file_size/1024:.2f} КБ)")
        
        # Проверяем файл
        with wave.open(filename, "rb") as wf:
            print(f"📊 Каналы: {wf.getnchannels()}")
            print(f"📊 Ширина сэмпла: {wf.getsampwidth()} байт")
            print(f"📊 Частота: {wf.getframerate()} Hz")
            print(f"📊 Количество фреймов: {wf.getnframes()}")
            print(f"📊 Длительность: {wf.getnframes()/wf.getframerate():.2f} сек")
        
        print_separator()
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("\n" + "=" * 60)
    print("🎤 ТЕСТ МИКРОФОНА ДЛЯ RASPBERRY PI")
    print("=" * 60 + "\n")
    
    audio = pyaudio.PyAudio()
    
    try:
        # 1. Показать все устройства
        list_audio_devices(audio)
        
        # 2. Получить устройство по умолчанию
        device_info = get_default_input_device(audio)
        if not device_info:
            print("❌ Не удалось получить устройство ввода!")
            return
        
        # 3. Протестировать частоты
        supported_rates = test_sample_rates(audio, device_info)
        
        if not supported_rates:
            print("❌ Ни одна частота дискретизации не поддерживается!")
            return
        
        # 4. Выбрать частоту для записи
        if SAMPLE_RATE in supported_rates:
            selected_rate = SAMPLE_RATE
            print(f"✅ Использую предпочтительную частоту: {selected_rate} Hz")
        else:
            selected_rate = supported_rates[0]
            print(f"⚠️ Частота {SAMPLE_RATE} Hz не поддерживается")
            print(f"✅ Использую первую доступную: {selected_rate} Hz")
        
        input("\n▶️ Нажмите Enter для начала записи...")
        
        # 5. Записать тестовое аудио
        frames, sample_rate = record_test_audio(audio, device_info, selected_rate)
        
        if not frames:
            print("❌ Запись не удалась!")
            return
        
        # 6. Сохранить в файл
        filename = save_wav_file(frames, sample_rate)
        
        if filename:
            print("\n" + "=" * 60)
            print("✅ ТЕСТ ЗАВЕРШЁН УСПЕШНО!")
            print("=" * 60)
            print(f"\n📁 Файл сохранён: {os.path.abspath(filename)}")
            print(f"\nВы можете прослушать файл с помощью:")
            print(f"  aplay {filename}")
            print(f"  или")
            print(f"  omxplayer {filename}")
            print("\n" + "=" * 60 + "\n")
        else:
            print("\n❌ ТЕСТ ЗАВЕРШЁН С ОШИБКАМИ")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Тест прерван пользователем")
    
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        audio.terminate()
        print("\n👋 Завершение работы...\n")

if __name__ == "__main__":
    main()
