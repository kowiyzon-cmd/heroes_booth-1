
import os
import requests
import logging
import urllib.request
from typing import Dict, List
from config import HERO_VIDEOS_PATH

logger = logging.getLogger(__name__)

class MediaManager:
    """Менеджер медиа-файлов"""
    
    def __init__(self):
        self.base_path = HERO_VIDEOS_PATH
        self._ensure_directories()
        
    def _ensure_directories(self):
        """Создать базовую директорию"""
        os.makedirs(self.base_path, exist_ok=True)
            
    def download_videos(self, heroes_data: Dict) -> bool:
        """
        Скачать видео для героев
        """
        logger.info("Началось скачивание видео")
        
        try:
            hero_names = heroes_data.get('hero_names', [])
            heroes_videos_data = heroes_data.get('heroes_data', {})
            
            logger.info(f"Обработка {len(hero_names)} героев: {hero_names}")
            
            total_downloaded = 0
            total_skipped = 0
            total_failed = 0
            
            for hero_name in hero_names:
                clean_hero_name = self._clean_filename(hero_name)
                hero_dir = os.path.join(self.base_path, clean_hero_name)
                os.makedirs(hero_dir, exist_ok=True)
                
                logger.info(f"Обработка героев: {hero_name} -> {hero_dir}")
                
                video_infos = heroes_videos_data.get(hero_name, [])
                logger.info(f"Найдено {len(video_infos)} видео для {hero_name}")
                
                for video_info in video_infos:
                    # Проверяем существование файла на сервере
                    if not video_info.get('exists', False):
                        logger.warning(f"Файл не существует {video_info.get('file_path')}")
                        total_failed += 1
                        continue
                    
                    success = self._download_single_video(video_info, hero_dir, video_info.get('id', 0))
                    if success:
                        total_downloaded += 1
                        logger.info(f"Successfully downloaded video for {hero_name}")
                    else:
                        total_failed += 1
                        logger.error(f"Failed to download video for {hero_name}")
            
            logger.info(f"Download summary: {total_downloaded} downloaded, {total_skipped} skipped, {total_failed} failed")
            return total_downloaded > 0
            
        except Exception as e:
            logger.error(f"Video download failed: {e}")
            return False
                
    def _clean_filename(self, name: str) -> str:
        """Очистить имя от недопустимых символов для файловой системы"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()
            
    

    def _download_single_video(self, video_info: Dict, target_dir: str, index: int) -> bool:
        """Скачать одно видео - используем реальные файловые пути"""
        try:
            # Используем ID записи как имя файла
            record_id = video_info.get('id')
            hero_name = video_info.get('hero_name', 'unknown')
            filename = f"{hero_name}_{record_id}.mp4"
            filepath = os.path.join(target_dir, filename)
            
            # Если видео уже существует, пропускаем скачивание
            if os.path.exists(filepath):
                logger.info(f"Видео существует: {filepath}")
                return True
            
            # Пробуем разные способы получить видео
            success = False
            
            # Способ 1: Используем реальный файловый путь с сервера Django
            server_file_path = video_info.get('file_path')
            if server_file_path and os.path.exists(server_file_path):
                logger.info(f"Серверный путь: {server_file_path}")
                try:
                    import shutil
                    shutil.copy2(server_file_path, filepath)
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"Успешно скопировано: {filename} ({os.path.getsize(filepath)} байт)")
                        success = True
                    else:
                        logger.error(f"Файл пустой: {filepath}")
                except Exception as copy_error:
                    logger.error(f"Ошибка копирования: {copy_error}")
            
            # Способ 2: Если файловый путь не сработал, пробуем скачать по URL
            if not success:
                video_url = video_info.get('url')
                if video_url:
                    # Создаем полный URL если нужно
                    if video_url.startswith('/'):
                        base_url = 'http://127.0.0.1:8000'  # Используем локальный адрес Django
                        video_url = base_url + video_url
                    
                    logger.info(f"Downloading from URL: {video_url}")
                    logger.info(f"Saving to: {filepath}")
                    
                    try:
                        import urllib.request
                        urllib.request.urlretrieve(video_url, filepath)
                        
                        # Проверяем что файл скачан
                        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                            logger.info(f"Успешно скачано: {filename} ({os.path.getsize(filepath)} bytes)")
                            success = True
                        else:
                            logger.error(f"Файл пустой: {filepath}")
                    except Exception as download_error:
                        logger.error(f"Ошибка скачивания: {download_error}")
            
            if not success:
                logger.error(f"Не удалось скачать {hero_name} видео {record_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Ошибка скачивания видео {video_info.get('id')}: {e}")
            return False
                
    def get_video_path(self, hero_name: str, video_index: int) -> str:
        """Получить путь к видеофайлу по имени героя и индексу видео"""
        clean_hero_name = self._clean_filename(hero_name)
        hero_dir = os.path.join(self.base_path, clean_hero_name)
        
        # Ищем все mp4 файлы в папке героя
        if os.path.exists(hero_dir):
            video_files = [f for f in os.listdir(hero_dir) if f.endswith('.mp4')]
            video_files.sort()  # Сортируем для consistency
            
            if video_index < len(video_files):
                return os.path.join(hero_dir, video_files[video_index])
        
        return None
        
    def get_hero_video_count(self, hero_name: str) -> int:
        """Получить количество видео для героя"""
        clean_hero_name = self._clean_filename(hero_name)
        hero_dir = os.path.join(self.base_path, clean_hero_name)
        if os.path.exists(hero_dir):
            return len([f for f in os.listdir(hero_dir) if f.endswith('.mp4')])
        return 0
        
    def get_all_hero_videos(self) -> Dict[str, List[str]]:
        """Получить все видео для всех героев"""
        result = {}
        
        if not os.path.exists(self.base_path):
            return result
            
        for hero_dir in os.listdir(self.base_path):
            hero_path = os.path.join(self.base_path, hero_dir)
            if os.path.isdir(hero_path):
                video_files = []
                for file in os.listdir(hero_path):
                    if file.endswith('.mp4'):
                        video_files.append(os.path.join(hero_path, file))
                video_files.sort()
                result[hero_dir] = video_files
                
        return result
