"""
Мощный файловый поисковик с современным GUI
Поддержка многопоточного поиска, regex, wildcards и множество фильтров
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import re
import mmap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
import json
import csv
from typing import List, Tuple, Optional
import fnmatch
from dataclasses import dataclass
import subprocess
from PIL import Image, ImageTk

# Попытка импорта GPU движка
try:
    from gpu_search_engine import HybridSearchEngine, GPU_AVAILABLE
    GPU_SUPPORT = True
    
    # Получаем информацию о GPU
    GPU_NAME = None
    GPU_MEMORY = None
    if GPU_AVAILABLE:
        # Сначала пробуем через nvidia-smi (более надежно)
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', 
                                   '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                info = result.stdout.strip().split(',')
                GPU_NAME = info[0].strip()
                GPU_MEMORY = float(info[1].strip()) / 1024  # МБ в ГБ
                print(f"✅ GPU найдена через nvidia-smi: {GPU_NAME} ({GPU_MEMORY:.1f} ГБ)")
        except Exception as e:
            print(f"⚠️ nvidia-smi не сработала: {e}")
        
        # Если не получилось, пробуем через numba
        if not GPU_NAME:
            try:
                from numba import cuda
                if cuda.is_available():
                    device = cuda.get_current_device()
                    GPU_NAME = device.name.decode()
                    GPU_MEMORY = device.total_memory / (1024**3)
                    print(f"✅ GPU найдена через numba: {GPU_NAME} ({GPU_MEMORY:.1f} ГБ)")
            except Exception as e:
                print(f"⚠️ numba cuda не сработала: {e}")
        
        # Если всё еще не получилось, ставим дефолтное значение
        if not GPU_NAME:
            GPU_NAME = "NVIDIA GPU (модель неизвестна)"
            print("⚠️ Не удалось определить модель GPU, используется дефолтное имя")
except ImportError:
    GPU_SUPPORT = False
    GPU_AVAILABLE = False
    GPU_NAME = None
    GPU_MEMORY = None


@dataclass
class SearchResult:
    """Результат поиска файла"""
    path: str
    size: int
    modified: datetime
    match_reason: str


class FileSearchEngine:
    """Ядро поисковой системы с многопоточностью и GPU ускорением"""
    
    def __init__(self, max_workers: Optional[int] = None, use_gpu: bool = False):
        self.max_workers = max_workers or os.cpu_count() or 4
        self.stop_flag = threading.Event()
        self.use_gpu = use_gpu and GPU_SUPPORT
        
        # Инициализация GPU движка если доступен
        if self.use_gpu:
            self.gpu_engine = HybridSearchEngine(use_gpu=True)
        else:
            self.gpu_engine = None
        
    def search(self, root_path: str, 
               name_pattern: str = "*",
               extensions: List[str] = None,
               content_regex: str = None,
               min_size: int = 0,
               max_size: int = None,
               modified_after: datetime = None,
               modified_before: datetime = None,
               case_sensitive: bool = False,
               use_regex_name: bool = False,
               callback=None) -> List[SearchResult]:
        """
        Выполняет многопоточный поиск файлов
        
        Args:
            root_path: Корневая директория для поиска
            name_pattern: Паттерн имени файла (wildcard или regex)
            extensions: Список расширений для фильтрации
            content_regex: Регулярное выражение для поиска в содержимом
            min_size: Минимальный размер файла в байтах
            max_size: Максимальный размер файла в байтах
            modified_after: Файлы модифицированные после этой даты
            modified_before: Файлы модифицированные до этой даты
            case_sensitive: Учитывать регистр при поиске
            use_regex_name: Использовать regex вместо wildcard для имени
            callback: Функция обратного вызова для обновления прогресса
        """
        self.stop_flag.clear()
        results = []
        
        # Компиляция регулярных выражений
        content_pattern = None
        if content_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                content_pattern = re.compile(content_regex, flags)
            except re.error as e:
                raise ValueError(f"Ошибка в регулярном выражении: {e}")
        
        name_regex = None
        if use_regex_name and name_pattern != "*":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                name_regex = re.compile(name_pattern, flags)
            except re.error as e:
                raise ValueError(f"Ошибка в регулярном выражении имени: {e}")
        
        # Нормализация расширений
        if extensions:
            extensions = [ext.lower().strip('.') for ext in extensions if ext.strip()]
        
        # Сбор всех файлов для обработки
        files_to_check = []
        try:
            for root, dirs, files in os.walk(root_path):
                if self.stop_flag.is_set():
                    break
                    
                # Фильтрация скрытых директорий для ускорения
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if self.stop_flag.is_set():
                        break
                    files_to_check.append(os.path.join(root, file))
                    
        except PermissionError:
            pass
        
        total_files = len(files_to_check)
        processed = 0
        
        # Многопоточная обработка файлов
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._check_file,
                    file_path,
                    name_pattern,
                    name_regex,
                    extensions,
                    content_pattern,
                    min_size,
                    max_size,
                    modified_after,
                    modified_before,
                    case_sensitive,
                    use_regex_name
                ): file_path
                for file_path in files_to_check
            }
            
            for future in as_completed(futures):
                if self.stop_flag.is_set():
                    break
                    
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        if callback:
                            callback(result, processed, total_files)
                except Exception:
                    pass  # Игнорируем ошибки отдельных файлов
                
                processed += 1
                if callback and processed % 100 == 0:
                    callback(None, processed, total_files)
        
        return results
    
    def _check_file(self, file_path: str, name_pattern: str, name_regex,
                   extensions, content_pattern, min_size, max_size,
                   modified_after, modified_before, case_sensitive,
                   use_regex_name) -> Optional[SearchResult]:
        """Проверяет один файл на соответствие критериям"""
        try:
            # Проверка на остановку
            if self.stop_flag.is_set():
                return None
            # Проверка существования
            if not os.path.isfile(file_path):
                return None
            
            filename = os.path.basename(file_path)
            
            # Проверка имени
            if use_regex_name and name_regex:
                if not name_regex.search(filename):
                    return None
            elif name_pattern != "*":
                if case_sensitive:
                    if not fnmatch.fnmatch(filename, name_pattern):
                        return None
                else:
                    if not fnmatch.fnmatch(filename.lower(), name_pattern.lower()):
                        return None
            
            # Проверка расширения
            if extensions:
                file_ext = os.path.splitext(filename)[1].lower().strip('.')
                if file_ext not in extensions:
                    return None
            
            # Получение метаданных
            stat = os.stat(file_path)
            file_size = stat.st_size
            file_modified = datetime.fromtimestamp(stat.st_mtime)
            
            # Проверка размера
            if min_size and file_size < min_size:
                return None
            if max_size and file_size > max_size:
                return None
            
            # Проверка даты модификации
            if modified_after and file_modified < modified_after:
                return None
            if modified_before and file_modified > modified_before:
                return None
            
            match_reason = "Имя файла"
            
            # Проверка содержимого (самая затратная операция)
            if content_pattern:
                if not self._search_in_file(file_path, content_pattern):
                    return None
                match_reason = "Содержимое файла"
            
            return SearchResult(
                path=file_path,
                size=file_size,
                modified=file_modified,
                match_reason=match_reason
            )
            
        except (PermissionError, OSError):
            return None
    
    def _search_in_file(self, file_path: str, pattern: re.Pattern) -> bool:
        """Быстрый поиск в файле с использованием memory-mapped I/O или GPU"""
        try:
            # Проверка на остановку
            if self.stop_flag.is_set():
                return False
            
            # Если GPU доступна, используем гибридный движок
            if self.use_gpu and self.gpu_engine:
                return self.gpu_engine.search_in_file(file_path, pattern)
            
            # Иначе стандартный CPU поиск
            file_size = os.path.getsize(file_path)
            
            # Ограничение размера файла для поиска в содержимом (100 МБ)
            if file_size > 100 * 1024 * 1024:
                return False
            
            # Пытаемся определить, является ли файл текстовым
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                if b'\x00' in chunk:  # Бинарный файл
                    return False
                
                # Для небольших файлов (<8KB)
                if len(chunk) < 8192:
                    try:
                        text = chunk.decode('utf-8', errors='ignore')
                        return bool(pattern.search(text))
                    except:
                        return False
            
            # Для средних файлов (до 5 МБ) читаем полностью
            # Но ограничиваем еще сильнее если regex сложный
            safe_limit = 5 * 1024 * 1024  # 5 МБ для обычных регулярок
            if self._is_dangerous_pattern(pattern):
                safe_limit = 1 * 1024 * 1024  # 1 МБ для опасных
            
            if file_size <= safe_limit:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    text = content.decode('utf-8', errors='ignore')
                    
                    # Проверка на остановку перед regex
                    if self.stop_flag.is_set():
                        return False
                    
                    # Применяем regex к небольшому тексту
                    try:
                        return bool(pattern.search(text))
                    except Exception as e:
                        print(f"⚠️ Regex ошибка в {os.path.basename(file_path)}: {e}")
                        return False
            
            # Для больших файлов используем mmap и чанки
            with open(file_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
                    # Размер чанка зависит от сложности regex
                    if self._is_dangerous_pattern(pattern):
                        chunk_size = 512 * 1024  # 512 КБ для опасных regex
                    else:
                        chunk_size = 5 * 1024 * 1024  # 5 МБ для обычных
                    
                    for offset in range(0, file_size, chunk_size):
                        # Проверка на остановку
                        if self.stop_flag.is_set():
                            return False
                        
                        # Читаем чанк с перекрытием (чтобы не пропустить совпадения на границе)
                        overlap = 1024  # 1KB перекрытие
                        start = max(0, offset - overlap)
                        end = min(file_size, offset + chunk_size)
                        
                        chunk_bytes = mmapped[start:end]
                        text = chunk_bytes.decode('utf-8', errors='ignore')
                        
                        # Применяем regex к чанку с защитой от ошибок
                        try:
                            if pattern.search(text):
                                return True
                        except Exception as e:
                            print(f"⚠️ Regex timeout/error в чанке {offset//chunk_size}: {e}")
                            # Пропускаем проблемный чанк
                            continue
                    
                    return False
                    
        except (PermissionError, OSError, UnicodeDecodeError, ValueError):
            return False
        except Exception as e:
            # Любые другие ошибки (включая зависания regex) - просто пропускаем
            print(f"⚠️ Ошибка при поиске в {file_path}: {e}")
            return False
    
    def _is_dangerous_pattern(self, pattern: re.Pattern) -> bool:
        """Проверяет, является ли скомпилированный паттерн опасным"""
        pattern_str = pattern.pattern
        
        # Опасные конструкции
        dangerous = [
            r'[\s\S]*', r'[\s\S]+',  # Очень опасно
            r'[\w\W]*', r'[\w\W]+',
            r'[\d\D]*', r'[\d\D]+',
            r'.*?', r'.+?',          # Ленивые квантификаторы
        ]
        
        for danger in dangerous:
            if danger in pattern_str:
                return True
        
        return False
    
    def stop(self):
        """Останавливает поиск"""
        self.stop_flag.set()
    
    def get_gpu_stats(self) -> Optional[dict]:
        """Возвращает статистику использования GPU"""
        if self.use_gpu and self.gpu_engine:
            return self.gpu_engine.get_stats()
        return None


class FileSearcherApp(ctk.CTk):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        
        # Настройка окна
        self.title("🔍 Мощный Файловый Поисковик")
        self.geometry("1600x900")
        
        # Устанавливаем иконку
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
            if os.path.exists(icon_path):
                icon_image = Image.open(icon_path)
                icon_photo = ImageTk.PhotoImage(icon_image)
                self.iconphoto(True, icon_photo)
                # Сохраняем ссылку чтобы не было удалено сборщиком мусора
                self._icon_photo = icon_photo
        except Exception as e:
            print(f"⚠️ Не удалось загрузить иконку: {e}")
        
        # Устанавливаем тему
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Переменные
        self.search_engine = FileSearchEngine()
        self.search_thread = None
        self.results = []
        self.filtered_results = []
        self.is_searching = False
        self.sort_column = None
        self.sort_reverse = False
        self.gpu_monitor_active = False
        
        # Создаем интерфейс
        self._create_widgets()
        
        # Биндинг для вставки из буфера (фикс для CustomTkinter)
        self._bind_paste_events()
        
        # Запускаем мониторинг GPU если доступен
        if GPU_AVAILABLE:
            self._start_gpu_monitoring()
        
    def _create_widgets(self):
        """Создает все виджеты интерфейса"""
        
        # Левая панель - критерии поиска
        left_panel = ctk.CTkFrame(self, width=400, corner_radius=10)
        left_panel.pack(side="left", fill="both", padx=10, pady=10)
        left_panel.pack_propagate(False)
        
        # Заголовок
        title = ctk.CTkLabel(left_panel, text="Критерии поиска", 
                            font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=10)
        
        # Директория поиска
        dir_frame = ctk.CTkFrame(left_panel)
        dir_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(dir_frame, text="📁 Директория:", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        dir_input_frame = ctk.CTkFrame(dir_frame)
        dir_input_frame.pack(fill="x", padx=5, pady=2)
        
        self.dir_entry = ctk.CTkEntry(dir_input_frame, placeholder_text="Выберите директорию...")
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(dir_input_frame, text="Обзор", width=70,
                     command=self._browse_directory).pack(side="right")
        
        # Имя файла
        name_frame = ctk.CTkFrame(left_panel)
        name_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(name_frame, text="📝 Имя файла:", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        self.name_entry = ctk.CTkEntry(name_frame, placeholder_text="*.txt или regex")
        self.name_entry.pack(fill="x", padx=5, pady=2)
        
        self.regex_name_check = ctk.CTkCheckBox(name_frame, text="Использовать regex")
        self.regex_name_check.pack(anchor="w", padx=5, pady=2)
        
        # Расширения
        ext_frame = ctk.CTkFrame(left_panel)
        ext_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(ext_frame, text="🗂️ Расширения (через запятую):", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        self.ext_entry = ctk.CTkEntry(ext_frame, placeholder_text="txt, pdf, docx")
        self.ext_entry.pack(fill="x", padx=5, pady=2)
        
        # Содержимое
        content_frame = ctk.CTkFrame(left_panel)
        content_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(content_frame, text="🔤 Поиск в содержимом (regex):", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        self.content_entry = ctk.CTkEntry(content_frame, placeholder_text=r"import\s+\w+")
        self.content_entry.pack(fill="x", padx=5, pady=2)
        
        self.case_sensitive_check = ctk.CTkCheckBox(content_frame, 
                                                     text="Учитывать регистр")
        self.case_sensitive_check.pack(anchor="w", padx=5, pady=2)
        
        # Размер файла
        size_frame = ctk.CTkFrame(left_panel)
        size_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(size_frame, text="💾 Размер файла (КБ):", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        size_inputs = ctk.CTkFrame(size_frame)
        size_inputs.pack(fill="x", padx=5, pady=2)
        
        ctk.CTkLabel(size_inputs, text="От:").pack(side="left", padx=5)
        self.min_size_entry = ctk.CTkEntry(size_inputs, width=80, placeholder_text="0")
        self.min_size_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(size_inputs, text="До:").pack(side="left", padx=5)
        self.max_size_entry = ctk.CTkEntry(size_inputs, width=80, placeholder_text="∞")
        self.max_size_entry.pack(side="left", padx=5)
        
        # Количество потоков
        threads_frame = ctk.CTkFrame(left_panel)
        threads_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(threads_frame, text="⚡ Потоков CPU:", 
                    font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)
        
        self.threads_slider = ctk.CTkSlider(threads_frame, from_=1, 
                                           to=os.cpu_count() * 2,
                                           number_of_steps=os.cpu_count() * 2 - 1)
        self.threads_slider.set(os.cpu_count())
        self.threads_slider.pack(fill="x", padx=5, pady=2)
        
        self.threads_label = ctk.CTkLabel(threads_frame, 
                                         text=f"Потоков: {os.cpu_count()}")
        self.threads_label.pack(padx=5, pady=2)
        
        self.threads_slider.configure(command=self._update_threads_label)
        
        # GPU ускорение
        gpu_frame = ctk.CTkFrame(left_panel)
        gpu_frame.pack(fill="x", padx=10, pady=5)
        
        if GPU_AVAILABLE:
            gpu_text = "🚀 GPU ускорение (CUDA)"
            gpu_color = "green"
        elif GPU_SUPPORT:
            gpu_text = "⚠️ GPU ускорение (нет CUDA)"
            gpu_color = "orange"
        else:
            gpu_text = "⚠️ GPU ускорение (не установлено)"
            gpu_color = "gray"
        
        gpu_label = ctk.CTkLabel(gpu_frame, text=gpu_text,
                                font=ctk.CTkFont(size=14, weight="bold"),
                                text_color=gpu_color)
        gpu_label.pack(anchor="w", padx=5, pady=2)
        
        # Информация о GPU - показываем если GPU доступна
        if GPU_AVAILABLE:
            # Модель GPU
            if GPU_NAME:
                gpu_model_text = f"🎮 {GPU_NAME}"
                if GPU_MEMORY:
                    gpu_model_text += f" ({GPU_MEMORY:.1f} ГБ)"
            else:
                gpu_model_text = "🎮 GPU обнаружена (модель определяется...)"
            
            self.gpu_model_label = ctk.CTkLabel(gpu_frame, 
                                               text=gpu_model_text,
                                               font=ctk.CTkFont(size=11),
                                               text_color="#4CAF50")
            self.gpu_model_label.pack(anchor="w", padx=5, pady=1)
            
            # Метка для загрузки GPU
            self.gpu_load_label = ctk.CTkLabel(gpu_frame,
                                              text="⚡ Загрузка GPU: -- | Память: --",
                                              font=ctk.CTkFont(size=10),
                                              text_color="gray")
            self.gpu_load_label.pack(anchor="w", padx=5, pady=1)
        
        self.gpu_check = ctk.CTkCheckBox(gpu_frame, 
                                        text="Использовать GPU для поиска в содержимом",
                                        state="normal" if GPU_AVAILABLE else "disabled")
        self.gpu_check.pack(anchor="w", padx=5, pady=2)
        
        if GPU_AVAILABLE:
            self.gpu_check.select()  # Включено по умолчанию
            gpu_info = ctk.CTkLabel(gpu_frame, 
                                   text="ℹ️ GPU ускоряет поиск в больших файлах (>1МБ)",
                                   font=ctk.CTkFont(size=10),
                                   text_color="gray")
            gpu_info.pack(anchor="w", padx=5, pady=2)
        
        # Кнопки управления
        buttons_frame = ctk.CTkFrame(left_panel)
        buttons_frame.pack(fill="x", padx=10, pady=20)
        
        self.search_button = ctk.CTkButton(buttons_frame, text="🔍 НАЧАТЬ ПОИСК",
                                          font=ctk.CTkFont(size=16, weight="bold"),
                                          height=50, fg_color="green",
                                          hover_color="darkgreen",
                                          command=self._start_search)
        self.search_button.pack(fill="x", padx=5, pady=5)
        
        self.stop_button = ctk.CTkButton(buttons_frame, text="⏹ ОСТАНОВИТЬ",
                                        font=ctk.CTkFont(size=16, weight="bold"),
                                        height=40, fg_color="red",
                                        hover_color="darkred",
                                        command=self._stop_search,
                                        state="disabled")
        self.stop_button.pack(fill="x", padx=5, pady=5)
        
        # Прогресс
        self.progress_bar = ctk.CTkProgressBar(left_panel)
        self.progress_bar.pack(fill="x", padx=10, pady=5)
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(left_panel, text="Готов к поиску",
                                        font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=5)
        
        # Правая панель - результаты
        right_panel = ctk.CTkFrame(self, corner_radius=10)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Заголовок результатов
        results_header = ctk.CTkFrame(right_panel)
        results_header.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(results_header, text="Результаты поиска", 
                    font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        
        self.results_count_label = ctk.CTkLabel(results_header, text="Найдено: 0",
                                               font=ctk.CTkFont(size=14))
        self.results_count_label.pack(side="right", padx=10)
        
        # Кнопки экспорта
        export_frame = ctk.CTkFrame(right_panel)
        export_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(export_frame, text="💾 Экспорт в CSV",
                     command=lambda: self._export_results("csv")).pack(side="left", padx=5)
        
        ctk.CTkButton(export_frame, text="📄 Экспорт в JSON",
                     command=lambda: self._export_results("json")).pack(side="left", padx=5)
        
        ctk.CTkButton(export_frame, text="📂 Открыть файл",
                     command=self._open_selected_file).pack(side="left", padx=5)
        
        ctk.CTkButton(export_frame, text="📁 Открыть папку",
                     command=self._open_selected_directory).pack(side="left", padx=5)
        
        ctk.CTkButton(export_frame, text="🗑️ Очистить",
                     command=self._clear_results).pack(side="right", padx=5)
        
        # Фильтр результатов
        filter_frame = ctk.CTkFrame(right_panel)
        filter_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(filter_frame, text="🔍 Фильтр:").pack(side="left", padx=5)
        
        self.filter_entry = ctk.CTkEntry(filter_frame, placeholder_text="Фильтр по имени файла...")
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.filter_entry.bind("<KeyRelease>", lambda e: self._apply_filter())
        
        ctk.CTkButton(filter_frame, text="❌", width=40,
                     command=self._clear_filter).pack(side="right", padx=5)
        
        # Таблица результатов с прокруткой
        table_frame = ctk.CTkFrame(right_panel)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Создаем Treeview с темной темой
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview",
                       background="#2b2b2b",
                       foreground="white",
                       fieldbackground="#2b2b2b",
                       borderwidth=0)
        style.configure("Treeview.Heading",
                       background="#1f538d",
                       foreground="white",
                       borderwidth=1)
        style.map('Treeview',
                 background=[('selected', '#1f538d')])
        
        # Скроллбары
        scrollbar_y = ttk.Scrollbar(table_frame, orient="vertical")
        scrollbar_y.pack(side="right", fill="y")
        
        scrollbar_x = ttk.Scrollbar(table_frame, orient="horizontal")
        scrollbar_x.pack(side="bottom", fill="x")
        
        # Таблица
        columns = ("filename", "size", "modified", "path")
        self.results_tree = ttk.Treeview(table_frame,
                                        columns=columns,
                                        show="headings",
                                        yscrollcommand=scrollbar_y.set,
                                        xscrollcommand=scrollbar_x.set,
                                        selectmode="browse")
        
        scrollbar_y.config(command=self.results_tree.yview)
        scrollbar_x.config(command=self.results_tree.xview)
        
        # Настройка колонок
        self.results_tree.heading("filename", text="📄 Имя файла", 
                                 command=lambda: self._sort_results("filename"))
        self.results_tree.heading("size", text="💾 Размер",
                                 command=lambda: self._sort_results("size"))
        self.results_tree.heading("modified", text="📅 Изменен",
                                 command=lambda: self._sort_results("modified"))
        self.results_tree.heading("path", text="📁 Путь",
                                 command=lambda: self._sort_results("path"))
        
        self.results_tree.column("filename", width=200, anchor="w")
        self.results_tree.column("size", width=100, anchor="e")
        self.results_tree.column("modified", width=150, anchor="center")
        self.results_tree.column("path", width=600, anchor="w")
        
        self.results_tree.pack(fill="both", expand=True)
        
        # Контекстное меню
        self.context_menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white",
                                    activebackground="#1f538d", activeforeground="white")
        self.context_menu.add_command(label="📂 Открыть файл", command=self._open_selected_file)
        self.context_menu.add_command(label="📁 Открыть папку", command=self._open_selected_directory)
        self.context_menu.add_command(label="📋 Копировать путь", command=self._copy_path)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ Удалить из списка", command=self._remove_selected)
        
        # Биндинги для таблицы
        self.results_tree.bind("<Double-1>", lambda e: self._open_selected_file())
        self.results_tree.bind("<Button-3>", self._show_context_menu)
        
        # Footer с авторством
        footer_frame = ctk.CTkFrame(right_panel, height=30)
        footer_frame.pack(fill="x", padx=10, pady=5)
        
        footer_label = ctk.CTkLabel(footer_frame,
                                    text="Made with ❤️ by alexander.kurskikh",
                                    font=ctk.CTkFont(size=10),
                                    text_color="gray")
        footer_label.pack(side="right", padx=10, pady=5)
        
    def _update_threads_label(self, value):
        """Обновляет метку количества потоков"""
        self.threads_label.configure(text=f"Потоков: {int(value)}")
    
    def _get_gpu_load(self) -> Tuple[float, float]:
        """
        Получает загрузку GPU и использование памяти
        Returns: (gpu_utilization%, memory_used%)
        """
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                values = result.stdout.strip().split(',')
                if len(values) >= 3:
                    gpu_util = float(values[0].strip())
                    mem_used = float(values[1].strip())
                    mem_total = float(values[2].strip())
                    mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                    return gpu_util, mem_percent
        except Exception as e:
            # Тихо игнорируем ошибки мониторинга
            pass
        return -1.0, -1.0  # -1 означает "недоступно"
    
    def _update_gpu_load_display(self):
        """Обновляет отображение загрузки GPU"""
        if not GPU_AVAILABLE or not hasattr(self, 'gpu_load_label'):
            return
        
        gpu_util, mem_percent = self._get_gpu_load()
        
        # Проверяем доступность данных
        if gpu_util < 0 or mem_percent < 0:
            # Данные недоступны
            text = "⚡ Загрузка GPU: -- | Память: --"
            color = "gray"
        else:
            # Цвет в зависимости от загрузки
            if self.is_searching:
                if gpu_util > 70:
                    color = "#FF5722"  # Красный - высокая загрузка
                elif gpu_util > 30:
                    color = "#FFC107"  # Желтый - средняя
                else:
                    color = "#4CAF50"  # Зеленый - низкая
            else:
                color = "gray"
            
            text = f"⚡ Загрузка GPU: {gpu_util:.0f}% | Память: {mem_percent:.0f}%"
        
        self.gpu_load_label.configure(text=text, text_color=color)
    
    def _start_gpu_monitoring(self):
        """Запускает периодический мониторинг GPU"""
        if not GPU_AVAILABLE:
            return
        
        self.gpu_monitor_active = True
        self._gpu_monitor_loop()
    
    def _gpu_monitor_loop(self):
        """Цикл мониторинга GPU"""
        if not self.gpu_monitor_active:
            return
        
        try:
            # Обновляем загрузку
            self._update_gpu_load_display()
            
            # Пытаемся определить модель если еще не определена
            if hasattr(self, 'gpu_model_label') and GPU_NAME and "определяется" in self.gpu_model_label.cget("text"):
                gpu_model_text = f"🎮 {GPU_NAME}"
                if GPU_MEMORY:
                    gpu_model_text += f" ({GPU_MEMORY:.1f} ГБ)"
                self.gpu_model_label.configure(text=gpu_model_text)
        except Exception as e:
            pass
        
        # Обновляем каждые 500мс во время поиска, 2 сек в простое
        interval = 500 if self.is_searching else 2000
        self.after(interval, self._gpu_monitor_loop)
        
    def _is_complex_regex(self, regex_str: str) -> bool:
        """Определяет, является ли регулярка потенциально опасной (может зависнуть)"""
        # Признаки сложных регулярок, которые могут вызвать катастрофический backtracking
        dangerous_patterns = [
            r'\*\s*\)',      # *)  - вложенные квантификаторы
            r'\+\s*\)',      # +)
            r'\*\s*\*',      # ** 
            r'\+\s*\+',      # ++
            r'\*\s*\+',      # *+
            r'\+\s*\*',      # +*
            r'\(\?\:.*\)\*', # (?:...)* - необязательная группа с *
            r'\(\?\:.*\)\+', # (?:...)+
            r'\[\\s\\S\]\*', # [\s\S]* - очень опасно!
            r'\[\\s\\S\]\+', # [\s\S]+ - тоже опасно
            r'\[\\w\\W\]\*', # [\w\W]* - аналогично
            r'\[\\w\\W\]\+', # [\w\W]+
            r'\[\\d\\D\]\*', # [\d\D]*
            r'\[\\d\\D\]\+', # [\d\D]+
            r'\.\*\?',       # .*? - ленивый квантификатор может зависнуть
            r'\.\+\?',       # .+?
        ]
        
        # Проверяем наличие опасных паттернов
        for pattern in dangerous_patterns:
            if re.search(pattern, regex_str):
                return True
        
        # Подсчет вложенных групп и квантификаторов
        nested_groups = regex_str.count('(')
        quantifiers = regex_str.count('*') + regex_str.count('+') + regex_str.count('{')
        
        # Если много вложенности и квантификаторов - это подозрительно
        if nested_groups > 8 and quantifiers > 10:  # Сделал строже
            return True
        
        # Очень длинная регулярка тоже подозрительна
        if len(regex_str) > 150:  # Сделал строже
            return True
        
        return False
    
    def _browse_directory(self):
        """Открывает диалог выбора директории"""
        directory = filedialog.askdirectory(title="Выберите директорию для поиска")
        if directory:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, directory)
    
    def _start_search(self):
        """Запускает поиск"""
        if self.is_searching:
            return
        
        # Валидация
        root_path = self.dir_entry.get().strip()
        if not root_path or not os.path.isdir(root_path):
            messagebox.showerror("Ошибка", "Выберите корректную директорию!")
            return
        
        # Подготовка параметров
        try:
            name_pattern = self.name_entry.get().strip() or "*"
            extensions = [e.strip() for e in self.ext_entry.get().split(",") if e.strip()]
            content_regex = self.content_entry.get().strip() or None
            
            # Предупреждение о сложных регулярках
            if content_regex and self._is_complex_regex(content_regex):
                result = messagebox.askokcancel(
                    "⚠️ Сложная регулярка",
                    "Обнаружена очень сложная регулярка!\n\n"
                    "Она может работать очень медленно или зависнуть на больших файлах.\n\n"
                    "Рекомендации:\n"
                    "• Упростите регулярку\n"
                    "• Ограничьте расширения файлов\n"
                    "• Уменьшите область поиска\n\n"
                    "Продолжить поиск?",
                    icon="warning"
                )
                if not result:
                    return
            
            min_size_str = self.min_size_entry.get().strip()
            min_size = int(float(min_size_str) * 1024) if min_size_str else 0
            
            max_size_str = self.max_size_entry.get().strip()
            max_size = int(float(max_size_str) * 1024) if max_size_str else None
            
            case_sensitive = self.case_sensitive_check.get()
            use_regex_name = self.regex_name_check.get()
            max_workers = int(self.threads_slider.get())
            use_gpu = self.gpu_check.get() if hasattr(self, 'gpu_check') else False
            
        except ValueError as e:
            messagebox.showerror("Ошибка", f"Некорректные параметры: {e}")
            return
        
        # Очистка предыдущих результатов
        self._clear_results()
        
        # Обновление UI
        self.is_searching = True
        self.search_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress_bar.set(0)
        
        # Статус с GPU инфо
        gpu_status = " (GPU включена)" if use_gpu and GPU_AVAILABLE else ""
        self.status_label.configure(text=f"Поиск...{gpu_status}")
        
        # Создаем новый search engine с нужным количеством потоков и GPU
        self.search_engine = FileSearchEngine(max_workers=max_workers, use_gpu=use_gpu)
        
        # Запуск в отдельном потоке
        self.search_thread = threading.Thread(
            target=self._search_worker,
            args=(root_path, name_pattern, extensions, content_regex,
                  min_size, max_size, case_sensitive, use_regex_name),
            daemon=True
        )
        self.search_thread.start()
    
    def _search_worker(self, root_path, name_pattern, extensions, content_regex,
                      min_size, max_size, case_sensitive, use_regex_name):
        """Рабочий поток для поиска"""
        try:
            results = self.search_engine.search(
                root_path=root_path,
                name_pattern=name_pattern,
                extensions=extensions or None,
                content_regex=content_regex,
                min_size=min_size,
                max_size=max_size,
                case_sensitive=case_sensitive,
                use_regex_name=use_regex_name,
                callback=self._search_callback
            )
            
            self.after(0, self._search_complete, results)
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка поиска", str(e)))
            self.after(0, self._search_complete, [])
    
    def _search_callback(self, result, processed, total):
        """Обратный вызов для обновления прогресса"""
        if result:
            self.after(0, self._add_result, result)
            # Обновляем статус с именем файла
            filename = os.path.basename(result.path)
            self.after(0, lambda: self.status_label.configure(
                text=f"Найдено: {len(self.results)} | Обработано: {processed}/{total} | ✓ {filename}"
            ))
        
        if total > 0:
            progress = processed / total
            self.after(0, self._update_progress, progress, processed, total)
    
    def _add_result(self, result: SearchResult):
        """Добавляет результат в список и таблицу"""
        self.results.append(result)
        self.filtered_results.append(result)
        
        # Форматирование данных
        filename = os.path.basename(result.path)
        size_str = self._format_size(result.size)
        date_str = result.modified.strftime("%Y-%m-%d %H:%M:%S")
        
        # Добавление в таблицу
        self.results_tree.insert("", "end", values=(
            filename,
            size_str,
            date_str,
            result.path
        ))
        
        self.results_count_label.configure(text=f"Найдено: {len(self.results)}")
    
    def _update_progress(self, progress, processed, total):
        """Обновляет прогресс-бар"""
        self.progress_bar.set(progress)
        # Не обновляем статус если он уже содержит информацию о найденных файлах
        current_text = self.status_label.cget("text")
        if "Найдено:" not in current_text:
            self.status_label.configure(text=f"Обработано: {processed} / {total}")
    
    def _search_complete(self, results):
        """Вызывается после завершения поиска"""
        self.is_searching = False
        self.search_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.progress_bar.set(1)
        
        # Статистика GPU
        gpu_stats_str = ""
        if self.search_engine.use_gpu:
            stats = self.search_engine.get_gpu_stats()
            if stats:
                gpu_searches = stats.get('gpu_searches', 0)
                cpu_searches = stats.get('cpu_searches', 0)
                gpu_stats_str = f" | GPU: {gpu_searches}, CPU: {cpu_searches}"
        
        self.status_label.configure(text=f"Поиск завершен! Найдено: {len(results)}{gpu_stats_str}")
        
        if not results:
            messagebox.showinfo("Поиск завершен", "Файлы не найдены")
        elif self.search_engine.use_gpu:
            # Показываем подробную статистику GPU
            stats = self.search_engine.get_gpu_stats()
            if stats and stats.get('gpu_searches', 0) > 0:
                info_msg = (
                    f"Найдено файлов: {len(results)}\n\n"
                    f"📊 Статистика GPU/CPU:\n"
                    f"GPU поисков: {stats.get('gpu_searches', 0)} ({stats.get('gpu_percentage', 0):.1f}%)\n"
                    f"CPU поисков: {stats.get('cpu_searches', 0)} ({stats.get('cpu_percentage', 0):.1f}%)\n"
                    f"GPU совпадений: {stats.get('gpu_hits', 0)}\n"
                    f"CPU совпадений: {stats.get('cpu_hits', 0)}"
                )
                messagebox.showinfo("Поиск завершен", info_msg)
    
    def _stop_search(self):
        """Останавливает поиск"""
        if self.is_searching:
            self.search_engine.stop()
            self.status_label.configure(text="Остановка поиска...")
            self.stop_button.configure(state="disabled")
    
    def _clear_results(self):
        """Очищает результаты"""
        self.results.clear()
        self.filtered_results.clear()
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.results_count_label.configure(text="Найдено: 0")
        self.progress_bar.set(0)
        if hasattr(self, 'filter_entry'):
            self.filter_entry.delete(0, "end")
    
    def _export_results(self, format_type):
        """Экспортирует результаты"""
        if not self.results:
            messagebox.showwarning("Предупреждение", "Нет результатов для экспорта")
            return
        
        if format_type == "csv":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV файлы", "*.csv")]
            )
            if file_path:
                self._export_to_csv(file_path)
                
        elif format_type == "json":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON файлы", "*.json")]
            )
            if file_path:
                self._export_to_json(file_path)
    
    def _export_to_csv(self, file_path):
        """Экспорт в CSV"""
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Путь", "Размер (байт)", "Дата изменения", "Причина"])
                
                for result in self.results:
                    writer.writerow([
                        result.path,
                        result.size,
                        result.modified.strftime("%Y-%m-%d %H:%M:%S"),
                        result.match_reason
                    ])
            
            messagebox.showinfo("Успех", f"Результаты экспортированы в {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать: {e}")
    
    def _export_to_json(self, file_path):
        """Экспорт в JSON"""
        try:
            data = [
                {
                    "path": result.path,
                    "size": result.size,
                    "modified": result.modified.strftime("%Y-%m-%d %H:%M:%S"),
                    "match_reason": result.match_reason
                }
                for result in self.results
            ]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("Успех", f"Результаты экспортированы в {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать: {e}")
    
    def _open_selected_file(self):
        """Открывает выбранный файл"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите файл")
            return
        
        item = self.results_tree.item(selection[0])
        file_path = item['values'][3]  # Путь в 4-й колонке
        
        try:
            os.startfile(file_path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
    
    def _open_selected_directory(self):
        """Открывает директорию выбранного файла"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите файл")
            return
        
        item = self.results_tree.item(selection[0])
        file_path = item['values'][3]  # Путь в 4-й колонке
        
        try:
            # Нормализуем путь для Windows и добавляем кавычки
            normalized_path = os.path.normpath(file_path)
            
            # Открываем Explorer с выделением файла
            # Используем /select, с кавычками вокруг пути для поддержки пробелов
            subprocess.run(f'explorer /select,"{normalized_path}"', shell=True)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть директорию: {e}")
    
    def _copy_path(self):
        """Копирует путь в буфер обмена"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        file_path = item['values'][3]
        
        self.clipboard_clear()
        self.clipboard_append(file_path)
        self.status_label.configure(text=f"Путь скопирован: {os.path.basename(file_path)}")
    
    def _remove_selected(self):
        """Удаляет выбранный элемент из списка"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        file_path = item['values'][3]
        
        # Удаляем из списков
        self.results = [r for r in self.results if r.path != file_path]
        self.filtered_results = [r for r in self.filtered_results if r.path != file_path]
        
        # Удаляем из таблицы
        self.results_tree.delete(selection[0])
        self.results_count_label.configure(text=f"Найдено: {len(self.results)}")
    
    def _show_context_menu(self, event):
        """Показывает контекстное меню"""
        # Выбираем элемент под курсором
        item = self.results_tree.identify_row(event.y)
        if item:
            self.results_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def _apply_filter(self):
        """Применяет фильтр к результатам"""
        filter_text = self.filter_entry.get().strip().lower()
        
        # Очищаем таблицу
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Фильтруем результаты
        self.filtered_results = []
        for result in self.results:
            filename = os.path.basename(result.path).lower()
            if not filter_text or filter_text in filename:
                self.filtered_results.append(result)
                
                size_str = self._format_size(result.size)
                date_str = result.modified.strftime("%Y-%m-%d %H:%M:%S")
                
                self.results_tree.insert("", "end", values=(
                    os.path.basename(result.path),
                    size_str,
                    date_str,
                    result.path
                ))
        
        # Обновляем счетчик
        if filter_text:
            self.results_count_label.configure(
                text=f"Найдено: {len(self.results)} (показано: {len(self.filtered_results)})"
            )
        else:
            self.results_count_label.configure(text=f"Найдено: {len(self.results)}")
    
    def _clear_filter(self):
        """Очищает фильтр"""
        self.filter_entry.delete(0, "end")
        self._apply_filter()
    
    def _sort_results(self, column):
        """Сортирует результаты по колонке"""
        # Определяем направление сортировки
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        
        # Получаем все элементы
        items = [(self.results_tree.set(item, column), item) 
                 for item in self.results_tree.get_children('')]
        
        # Сортируем
        if column == "size":
            # Для размера конвертируем обратно в байты
            def size_to_bytes(size_str):
                if 'ГБ' in size_str:
                    return float(size_str.split()[0]) * 1024 * 1024 * 1024
                elif 'МБ' in size_str:
                    return float(size_str.split()[0]) * 1024 * 1024
                elif 'КБ' in size_str:
                    return float(size_str.split()[0]) * 1024
                else:
                    return float(size_str.split()[0])
            
            items.sort(key=lambda x: size_to_bytes(x[0]), reverse=self.sort_reverse)
        else:
            items.sort(key=lambda x: x[0], reverse=self.sort_reverse)
        
        # Переставляем элементы
        for index, (val, item) in enumerate(items):
            self.results_tree.move(item, '', index)
        
        # Обновляем заголовок
        for col in ("filename", "size", "modified", "path"):
            if col == column:
                arrow = " ▼" if self.sort_reverse else " ▲"
                self.results_tree.heading(col, 
                    text=self.results_tree.heading(col)['text'].split()[0] + " " + 
                         self.results_tree.heading(col)['text'].split()[1] + arrow)
            else:
                # Убираем стрелки с других колонок
                text = self.results_tree.heading(col)['text']
                if "▼" in text or "▲" in text:
                    self.results_tree.heading(col, text=text.replace(" ▼", "").replace(" ▲", ""))
    
    def _bind_paste_events(self):
        """Биндинг Ctrl+V для всех Entry виджетов (фикс CustomTkinter)"""
        # Сначала собираем список всех Entry виджетов
        entry_widgets = [
            self.dir_entry, 
            self.name_entry, 
            self.ext_entry, 
            self.content_entry, 
            self.min_size_entry, 
            self.max_size_entry
        ]
        
        # Добавляем filter_entry если он существует
        if hasattr(self, 'filter_entry'):
            entry_widgets.append(self.filter_entry)
        
        # Определяем обработчик вставки
        def paste_handler(event):
            try:
                # Получаем виджет - может быть внутренний tkinter виджет
                widget = event.widget
                
                # Находим родительский CTkEntry
                ctk_widget = None
                for entry in entry_widgets:
                    if hasattr(entry, '_entry') and entry._entry == widget:
                        ctk_widget = entry
                        break
                    elif entry == widget:
                        ctk_widget = entry
                        break
                
                if not ctk_widget:
                    return "break"
                
                # Получаем текст из буфера
                clipboard_text = self.clipboard_get()
                
                # Вставляем через метод CTkEntry
                if hasattr(ctk_widget, '_entry'):
                    # CustomTkinter использует внутренний _entry
                    internal_entry = ctk_widget._entry
                    try:
                        cursor_pos = internal_entry.index(tk.INSERT)
                        internal_entry.insert(cursor_pos, clipboard_text)
                    except:
                        # Fallback - вставляем в конец
                        internal_entry.insert(tk.END, clipboard_text)
                else:
                    # Стандартный Entry
                    try:
                        cursor_pos = ctk_widget.index(tk.INSERT)
                        ctk_widget.insert(cursor_pos, clipboard_text)
                    except:
                        ctk_widget.insert(tk.END, clipboard_text)
                
                return "break"
                
            except Exception as e:
                print(f"⚠️ Paste error: {e}")
                return "break"
        
        # Биндим события к каждому виджету И его внутреннему _entry
        for widget in entry_widgets:
            if widget:
                # Биндим к главному виджету
                widget.bind("<Control-v>", paste_handler)
                widget.bind("<Control-V>", paste_handler)
                
                # Также биндим к внутреннему tkinter Entry если он есть
                if hasattr(widget, '_entry'):
                    widget._entry.bind("<Control-v>", paste_handler)
                    widget._entry.bind("<Control-V>", paste_handler)
    
    @staticmethod
    def _format_size(size_bytes):
        """Форматирует размер файла"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} ПБ"


def main():
    """Точка входа в приложение"""
    app = FileSearcherApp()
    app.mainloop()


if __name__ == "__main__":
    main()

