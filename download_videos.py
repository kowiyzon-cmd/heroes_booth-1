# download_videos.py
import os
import requests
import zipfile
import config
from pathlib import Path
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def download_videos():
    """Основная функция для скачивания видео"""
    
    # Формируем URL для запроса
    url = f"{config.BASE_URL.rstrip('/')}/api/download-videos/{config.SUBCATEGORY_ID}/"
    
    # Заголовки запроса
    headers = {
        'Authorization': f'Bearer {config.API_TOKEN}',
        'Accept': 'application/zip'
    }
    
    logger.info(f"Подключаюсь к {url}")
    logger.info(f"Скачиваю видео для подкатегории ID: {config.SUBCATEGORY_ID}")
    
    try:
        # Отправляем запрос
        response = requests.get(url, headers=headers, stream=True, timeout=300)
        
        # Проверяем статус ответа
        if response.status_code == 200:
            # Сохраняем временный zip-файл
            zip_path = f"temp_videos_{config.SUBCATEGORY_ID}.zip"
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"ZIP-архив скачан: {zip_path}")
            
            # Распаковываем архив
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Создаем папку для видео, если её нет
                os.makedirs(config.HERO_VIDEOS_DIR, exist_ok=True)
                
                # Извлекаем все файлы
                zip_ref.extractall(config.HERO_VIDEOS_DIR)
                
                # Логируем извлеченные файлы
                for file_info in zip_ref.infolist():
                    extracted_path = os.path.join(config.HERO_VIDEOS_DIR, file_info.filename)
                    if os.path.isfile(extracted_path):
                        logger.info(f"Извлечен: {extracted_path}")
            
            # Удаляем временный zip-файл
            os.remove(zip_path)
            logger.info(f"Временный файл {zip_path} удален")
            
            # Выводим статистику
            count_videos()
            
        elif response.status_code == 401:
            logger.error("Ошибка авторизации: неверный или отсутствующий токен")
        elif response.status_code == 403:
            logger.error("Ошибка авторизации: неверный токен")
        elif response.status_code == 404:
            logger.error(f"Подкатегория с ID {config.SUBCATEGORY_ID} не найдена или нет видео")
        else:
            logger.error(f"Ошибка сервера: {response.status_code}")
            logger.error(f"Ответ: {response.text}")
            
    except requests.exceptions.ConnectionError:
        logger.error(f"Не удалось подключиться к серверу {config.BASE_URL}")
    except requests.exceptions.Timeout:
        logger.error("Таймаут при выполнении запроса")
    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")

def count_videos():
    """Подсчитывает количество скачанных видео и выводит статистику"""
    try:
        total_files = 0
        hero_stats = {}
        
        # Проверяем существование директории
        if os.path.exists(config.HERO_VIDEOS_DIR):
            # Проходим по всем подпапкам
            for hero_dir in os.listdir(config.HERO_VIDEOS_DIR):
                hero_path = os.path.join(config.HERO_VIDEOS_DIR, hero_dir)
                
                if os.path.isdir(hero_path):
                    # Считаем видеофайлы в папке героя
                    video_files = [f for f in os.listdir(hero_path) 
                                  if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]
                    
                    count = len(video_files)
                    hero_stats[hero_dir] = count
                    total_files += count
        
        # Выводим статистику
        logger.info("=" * 50)
        logger.info("СТАТИСТИКА СКАЧИВАНИЯ:")
        logger.info(f"Всего видео: {total_files}")
        
        for hero, count in hero_stats.items():
            logger.info(f"  {hero}: {count} видео")
            
        if total_files == 0:
            logger.warning("Не найдено видеофайлов. Проверьте структуру архива.")
        
    except Exception as e:
        logger.error(f"Ошибка при подсчете видео: {str(e)}")

def list_video_files():
    """Выводит список всех скачанных видеофайлов"""
    logger.info("Список скачанных видеофайлов:")
    logger.info("=" * 50)
    
    try:
        if os.path.exists(config.HERO_VIDEOS_DIR):
            for root, dirs, files in os.walk(config.HERO_VIDEOS_DIR):
                for file in files:
                    if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, config.HERO_VIDEOS_DIR)
                        file_size = os.path.getsize(file_path) / (1024 * 1024)  # В МБ
                        logger.info(f"{relative_path} ({file_size:.2f} MB)")
        else:
            logger.warning("Папка с видео не найдена")
    except Exception as e:
        logger.error(f"Ошибка при чтении файлов: {str(e)}")

if __name__ == "__main__":
    logger.info("Запуск скрипта скачивания видео...")
    logger.info(f"BASE_URL: {config.BASE_URL}")
    logger.info(f"Папка назначения: {config.HERO_VIDEOS_DIR}")
    
    download_videos()
    
    # Дополнительно: показать список файлов
    list_video_files()
    
    logger.info("Скрипт завершен.")
