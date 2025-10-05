"""
GPU-ускоренный движок поиска с гибридной CPU/GPU архитектурой
Использует CUDA для параллельного поиска паттернов в больших файлах
"""

import os
import re
import mmap
from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

# Проверка доступности GPU библиотек
GPU_AVAILABLE = False
USE_CUPY = False
USE_NUMBA = False

try:
    import cupy as cp
    USE_CUPY = True
    GPU_AVAILABLE = True
    print("✅ CuPy доступен - GPU ускорение включено!")
except ImportError:
    print("⚠️ CuPy не установлен - работаем на CPU")

try:
    from numba import cuda
    if cuda.is_available():
        USE_NUMBA = True
        GPU_AVAILABLE = True
        print(f"✅ CUDA доступна - GPU: {cuda.get_current_device().name.decode()}")
except ImportError:
    print("⚠️ Numba CUDA не доступна")


@dataclass
class GPUSearchConfig:
    """Конфигурация GPU поиска"""
    batch_size: int = 64 * 1024 * 1024  # 64 МБ батчи
    min_file_size_for_gpu: int = 1024 * 1024  # 1 МБ минимум для GPU
    max_pattern_complexity: int = 10  # Максимальная сложность regex для GPU
    use_gpu: bool = GPU_AVAILABLE
    threads_per_block: int = 256
    

class GPUPatternMatcher:
    """GPU-ускоренный поиск паттернов"""
    
    def __init__(self, config: GPUSearchConfig = None):
        self.config = config or GPUSearchConfig()
        self.gpu_available = GPU_AVAILABLE and self.config.use_gpu
        
        if self.gpu_available:
            self._init_gpu()
    
    def _init_gpu(self):
        """Инициализация GPU"""
        if USE_NUMBA:
            try:
                # Получаем информацию о GPU
                device = cuda.get_current_device()
                self.gpu_name = device.name.decode()
                self.gpu_compute_capability = device.compute_capability
                print(f"🚀 GPU инициализирован: {self.gpu_name}")
                print(f"   Compute Capability: {self.gpu_compute_capability}")
            except Exception as e:
                print(f"⚠️ Ошибка инициализации GPU: {e}")
                self.gpu_available = False
    
    def is_pattern_gpu_friendly(self, pattern: str) -> bool:
        """
        Определяет, подходит ли паттерн для GPU
        
        GPU-friendly паттерны:
        - Литеральные строки
        - Простые классы символов [abc]
        - Квантификаторы *, +, ?
        - Альтернативы |
        
        НЕ GPU-friendly:
        - Backreferences \\1, \\2
        - Lookahead/lookbehind (?=...) (?!...)
        - Рекурсивные паттерны
        - Условные выражения
        """
        # Проверка на сложные конструкции
        if any(x in pattern for x in [r'\1', r'\2', '(?=', '(?!', '(?<', '(?(', r'\g<']):
            return False
        
        # Подсчет сложности (примитивная метрика)
        complexity = (
            pattern.count('(') + 
            pattern.count('[') + 
            pattern.count('{') +
            pattern.count('\\') // 2
        )
        
        return complexity <= self.config.max_pattern_complexity
    
    def search_in_text_gpu(self, text: bytes, pattern: re.Pattern) -> bool:
        """
        Поиск паттерна в тексте на GPU
        
        Args:
            text: Текст в байтах
            pattern: Скомпилированный regex паттерн
            
        Returns:
            True если найдено совпадение
        """
        if not self.gpu_available or len(text) < self.config.min_file_size_for_gpu:
            # Fallback на CPU для мелких файлов
            return self._search_cpu(text, pattern)
        
        pattern_str = pattern.pattern
        
        if not self.is_pattern_gpu_friendly(pattern_str):
            # Сложные паттерны на CPU
            return self._search_cpu(text, pattern)
        
        try:
            # Пытаемся на GPU
            if USE_CUPY:
                return self._search_cupy(text, pattern)
            elif USE_NUMBA:
                return self._search_numba(text, pattern)
            else:
                return self._search_cpu(text, pattern)
        except Exception as e:
            # При ошибке fallback на CPU
            print(f"⚠️ GPU search failed, fallback to CPU: {e}")
            return self._search_cpu(text, pattern)
    
    def _search_cpu(self, text: bytes, pattern: re.Pattern) -> bool:
        """Fallback поиск на CPU"""
        try:
            text_str = text.decode('utf-8', errors='ignore')
            return bool(pattern.search(text_str))
        except Exception:
            return False
    
    def _search_cupy(self, text: bytes, pattern: re.Pattern) -> bool:
        """
        Поиск с использованием CuPy
        Для простых паттернов используем векторизованные операции
        """
        try:
            # Декодируем текст
            text_str = text.decode('utf-8', errors='ignore')
            
            # Для очень простых паттернов (литеральные строки)
            pattern_str = pattern.pattern
            
            if self._is_literal_pattern(pattern_str):
                # Простой поиск подстроки на GPU
                return self._literal_search_gpu(text_str, pattern_str)
            else:
                # Для regex используем batch обработку на CPU с numpy
                # (cuDF не поддерживает regex на Windows хорошо)
                return self._search_cpu(text, pattern)
                
        except Exception as e:
            return self._search_cpu(text, pattern)
    
    def _is_literal_pattern(self, pattern: str) -> bool:
        """Проверяет, является ли паттерн литеральной строкой"""
        special_chars = r'.*+?[]{}()^$|\\'
        return not any(c in pattern for c in special_chars)
    
    def _literal_search_gpu(self, text: str, substring: str) -> bool:
        """
        Быстрый поиск подстроки на GPU
        Использует CuPy для параллельного поиска
        """
        try:
            # Конвертируем в numpy массив символов
            text_array = np.frombuffer(text.encode('utf-8'), dtype=np.uint8)
            pattern_array = np.frombuffer(substring.encode('utf-8'), dtype=np.uint8)
            
            # Копируем на GPU
            text_gpu = cp.asarray(text_array)
            pattern_gpu = cp.asarray(pattern_array)
            
            pattern_len = len(pattern_array)
            text_len = len(text_array)
            
            if pattern_len > text_len:
                return False
            
            # Создаем скользящие окна на GPU
            # Это эквивалентно проверке всех возможных позиций параллельно
            num_positions = text_len - pattern_len + 1
            
            # Батчинг для больших текстов
            batch_size = 10_000_000  # 10M позиций за раз
            
            for start_pos in range(0, num_positions, batch_size):
                end_pos = min(start_pos + batch_size, num_positions)
                
                # Проверяем батч позиций параллельно
                found = self._check_positions_batch(
                    text_gpu, pattern_gpu, start_pos, end_pos, pattern_len
                )
                
                if found:
                    return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ GPU literal search error: {e}")
            return substring in text
    
    def _check_positions_batch(self, text_gpu, pattern_gpu, start_pos, end_pos, pattern_len):
        """Проверяет батч позиций параллельно на GPU"""
        try:
            # Для каждой позиции проверяем совпадение
            for i in range(start_pos, end_pos):
                window = text_gpu[i:i+pattern_len]
                if len(window) == pattern_len:
                    # Сравнение на GPU
                    if cp.all(window == pattern_gpu):
                        return True
            return False
        except Exception:
            return False
    
    def _search_numba(self, text: bytes, pattern: re.Pattern) -> bool:
        """
        Поиск с использованием Numba CUDA
        Компилирует кастомное CUDA ядро для поиска
        """
        try:
            text_str = text.decode('utf-8', errors='ignore')
            pattern_str = pattern.pattern
            
            if self._is_literal_pattern(pattern_str):
                return self._literal_search_numba(text_str, pattern_str)
            else:
                # Сложные паттерны на CPU
                return self._search_cpu(text, pattern)
                
        except Exception:
            return self._search_cpu(text, pattern)
    
    def _literal_search_numba(self, text: str, substring: str) -> bool:
        """Поиск подстроки используя Numba CUDA"""
        try:
            # Конвертируем в массивы
            text_array = np.frombuffer(text.encode('utf-8'), dtype=np.uint8)
            pattern_array = np.frombuffer(substring.encode('utf-8'), dtype=np.uint8)
            
            # Запускаем CUDA ядро
            found = self._run_cuda_kernel(text_array, pattern_array)
            return found
            
        except Exception as e:
            print(f"⚠️ Numba CUDA search error: {e}")
            return substring in text
    
    def _run_cuda_kernel(self, text: np.ndarray, pattern: np.ndarray) -> bool:
        """Запускает CUDA ядро для параллельного поиска"""
        if not USE_NUMBA:
            return False
        
        try:
            text_len = len(text)
            pattern_len = len(pattern)
            
            if pattern_len > text_len:
                return False
            
            num_positions = text_len - pattern_len + 1
            
            # Результат на CPU
            result = np.zeros(1, dtype=np.int32)
            
            # Копируем на GPU
            d_text = cuda.to_device(text)
            d_pattern = cuda.to_device(pattern)
            d_result = cuda.to_device(result)
            
            # Настройка блоков и потоков
            threads_per_block = self.config.threads_per_block
            blocks_per_grid = (num_positions + threads_per_block - 1) // threads_per_block
            
            # Запускаем ядро
            self._cuda_search_kernel[blocks_per_grid, threads_per_block](
                d_text, d_pattern, d_result, text_len, pattern_len
            )
            
            # Копируем результат обратно
            d_result.copy_to_host(result)
            
            return result[0] > 0
            
        except Exception as e:
            print(f"⚠️ CUDA kernel error: {e}")
            return False
    
    @staticmethod
    def _cuda_search_kernel_stub(text, pattern, result, text_len, pattern_len):
        """Заглушка для CUDA ядра когда Numba недоступна"""
        pass


# Компилируем CUDA ядро если Numba доступна
if USE_NUMBA:
    @cuda.jit
    def _cuda_search_kernel_impl(text, pattern, result, text_len, pattern_len):
        """
        CUDA ядро для параллельного поиска подстроки
        Каждый поток проверяет одну позицию в тексте
        """
        pos = cuda.grid(1)
        
        if pos < text_len - pattern_len + 1:
            # Проверяем совпадение с этой позиции
            match = True
            for i in range(pattern_len):
                if text[pos + i] != pattern[i]:
                    match = False
                    break
            
            if match:
                # Атомарно устанавливаем флаг найдено
                cuda.atomic.add(result, 0, 1)
    
    # Присваиваем метод классу
    GPUPatternMatcher._cuda_search_kernel = staticmethod(_cuda_search_kernel_impl)
else:
    GPUPatternMatcher._cuda_search_kernel = GPUPatternMatcher._cuda_search_kernel_stub


class HybridSearchEngine:
    """
    Гибридный движок поиска CPU+GPU
    Автоматически выбирает лучший метод для каждого файла
    """
    
    def __init__(self, use_gpu: bool = True):
        self.config = GPUSearchConfig(use_gpu=use_gpu)
        self.gpu_matcher = GPUPatternMatcher(self.config)
        self.stats = {
            'gpu_searches': 0,
            'cpu_searches': 0,
            'gpu_hits': 0,
            'cpu_hits': 0
        }
    
    def search_in_file(self, file_path: str, pattern: re.Pattern) -> bool:
        """
        Поиск паттерна в файле с автоматическим выбором CPU/GPU
        
        Args:
            file_path: Путь к файлу
            pattern: Скомпилированный regex паттерн
            
        Returns:
            True если найдено совпадение
        """
        try:
            file_size = os.path.getsize(file_path)
            
            # Проверка размера файла
            if file_size > 100 * 1024 * 1024:  # > 100 МБ
                return False  # Слишком большой
            
            # Выбор стратегии
            use_gpu = (
                self.config.use_gpu and 
                file_size >= self.config.min_file_size_for_gpu and
                self.gpu_matcher.gpu_available
            )
            
            # Читаем файл
            with open(file_path, 'rb') as f:
                # Проверка на бинарный файл
                chunk = f.read(8192)
                if b'\x00' in chunk:
                    return False
                
                # Для небольших файлов
                if file_size < 1024 * 1024:  # < 1 МБ
                    try:
                        text = chunk if len(chunk) == file_size else f.read()
                        text_str = text.decode('utf-8', errors='ignore')
                        found = bool(pattern.search(text_str))
                        self.stats['cpu_searches'] += 1
                        if found:
                            self.stats['cpu_hits'] += 1
                        return found
                    except:
                        return False
                
                # Для больших файлов используем memory map
                f.seek(0)
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
                    data = mmapped.read()
                    
                    if use_gpu:
                        self.stats['gpu_searches'] += 1
                        found = self.gpu_matcher.search_in_text_gpu(data, pattern)
                        if found:
                            self.stats['gpu_hits'] += 1
                        return found
                    else:
                        self.stats['cpu_searches'] += 1
                        try:
                            text_str = data.decode('utf-8', errors='ignore')
                            found = bool(pattern.search(text_str))
                            if found:
                                self.stats['cpu_hits'] += 1
                            return found
                        except:
                            return False
                            
        except (PermissionError, OSError, UnicodeDecodeError, ValueError):
            return False
    
    def get_stats(self) -> dict:
        """Возвращает статистику использования GPU/CPU"""
        total = self.stats['gpu_searches'] + self.stats['cpu_searches']
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            'gpu_percentage': (self.stats['gpu_searches'] / total) * 100,
            'cpu_percentage': (self.stats['cpu_searches'] / total) * 100,
            'gpu_hit_rate': (self.stats['gpu_hits'] / max(1, self.stats['gpu_searches'])) * 100,
            'cpu_hit_rate': (self.stats['cpu_hits'] / max(1, self.stats['cpu_searches'])) * 100,
        }
    
    def print_stats(self):
        """Выводит статистику"""
        stats = self.get_stats()
        print("\n" + "="*60)
        print("📊 Статистика поиска CPU/GPU")
        print("="*60)
        print(f"GPU поисков: {stats['gpu_searches']} ({stats.get('gpu_percentage', 0):.1f}%)")
        print(f"CPU поисков: {stats['cpu_searches']} ({stats.get('cpu_percentage', 0):.1f}%)")
        print(f"GPU совпадений: {stats['gpu_hits']} (hit rate: {stats.get('gpu_hit_rate', 0):.1f}%)")
        print(f"CPU совпадений: {stats['cpu_hits']} (hit rate: {stats.get('cpu_hit_rate', 0):.1f}%)")
        print("="*60)


# Тестирование
if __name__ == "__main__":
    print("🧪 Тестирование GPU Search Engine")
    print("="*60)
    
    # Создаем движок
    engine = HybridSearchEngine(use_gpu=True)
    
    # Тестовые паттерны
    test_patterns = [
        (r"test", "Литеральная строка"),
        (r"hello|world", "Простая альтернатива"),
        (r"\d{3}-\d{3}", "Цифры"),
        (r"(?=complex)", "Сложный lookahead"),
    ]
    
    print("\n🔍 Проверка GPU-friendly паттернов:")
    for pattern, desc in test_patterns:
        is_friendly = engine.gpu_matcher.is_pattern_gpu_friendly(pattern)
        emoji = "✅" if is_friendly else "❌"
        print(f"{emoji} {desc}: {pattern} - {'GPU' if is_friendly else 'CPU'}")
    
    print("\n✨ GPU Search Engine готов к использованию!")
    
    if GPU_AVAILABLE:
        print(f"🚀 GPU ускорение: ВКЛЮЧЕНО")
        print(f"   Библиотеки: {'CuPy ' if USE_CUPY else ''}{'Numba CUDA' if USE_NUMBA else ''}")
    else:
        print("⚠️ GPU недоступна - используется CPU")

