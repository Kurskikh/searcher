# 🔥 Расширенное использование

## 🎛️ Настройка производительности

### Оптимальное количество потоков

#### Для разных сценариев:

**Легкий поиск (только по имени)**
- **Рекомендация**: Количество ядер CPU
- **Почему**: Достаточно для быстрого обхода файловой системы

**Поиск по содержимому**
- **Рекомендация**: 2× количество ядер CPU
- **Почему**: I/O операции позволяют использовать больше потоков

**Медленный диск (HDD)**
- **Рекомендация**: Количество ядер CPU
- **Почему**: HDD не справляется с большим количеством параллельных запросов

**Быстрый диск (SSD/NVMe)**
- **Рекомендация**: 2-4× количество ядер CPU
- **Почему**: SSD отлично работает с параллельными запросами

**Сетевой диск**
- **Рекомендация**: 1-2 потока
- **Почему**: Сетевые задержки делают многопоточность неэффективной

---

## 🧪 Продвинутые Regex паттерны

### 1. Поиск кредитных карт
```regex
\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b
```

### 2. Поиск хэшей (MD5, SHA1)
```regex
\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b
```

### 3. Поиск паролей в коде
```regex
(password|passwd|pwd|pass)\s*[:=]\s*['"]\w+['"]
```

### 4. Поиск SQL запросов
```regex
(SELECT|INSERT|UPDATE|DELETE)\s+.+\s+(FROM|INTO)\s+
```

### 5. Поиск путей Windows
```regex
[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*
```

### 6. Поиск JSON объектов
```regex
\{[^{}]*:[^{}]*\}
```

### 7. Поиск IPv6 адресов
```regex
([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}
```

### 8. Поиск MAC адресов
```regex
([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})
```

### 9. Поиск шестнадцатеричных цветов
```regex
#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b
```

### 10. Поиск версий (semver)
```regex
\b\d+\.\d+\.\d+\b
```

---

## 🔍 Комплексные примеры поиска

### Аудит безопасности кода

**Цель**: Найти потенциальные уязвимости

```
Расширения: py, js, php, java
Содержимое: (eval\(|exec\(|system\(|shell_exec|passthru|popen)
Учитывать регистр: Нет
```

### Поиск утечек данных

**Цель**: Найти файлы с приватными ключами

```
Расширения: pem, key, ppk
Содержимое: (PRIVATE KEY|BEGIN RSA|BEGIN OPENSSH)
```

### Анализ импортов в Python проекте

**Цель**: Найти все файлы, использующие определенную библиотеку

```
Имя: *.py
Содержимое: ^import\s+(pandas|numpy|torch|tensorflow)
```

### Поиск устаревшего кода

**Цель**: Найти использование deprecated функций

```
Расширения: py, js
Содержимое: (deprecated|obsolete|legacy|FIXME|XXX)
```

### Поиск конфигураций баз данных

**Цель**: Найти файлы с подключениями к БД

```
Расширения: py, js, php, yaml, env
Содержимое: (mongodb://|mysql://|postgresql://|DATABASE_URL)
```

---

## 💻 Модификация кода

### Добавление новых функций

#### 1. Добавить сортировку результатов

В классе `FileSearcherApp`, метод `_add_result`:

```python
def _add_result(self, result: SearchResult):
    """Добавляет результат в список"""
    self.results.append(result)
    
    # НОВОЕ: Сортировка по размеру (по убыванию)
    self.results.sort(key=lambda r: r.size, reverse=True)
    
    # Перерисовка всех результатов
    self._refresh_results_display()
```

#### 2. Добавить фильтр по дате

Добавьте в `_create_widgets`:

```python
# Дата модификации
date_frame = ctk.CTkFrame(left_panel)
date_frame.pack(fill="x", padx=10, pady=5)

ctk.CTkLabel(date_frame, text="📅 Изменен после:", 
            font=ctk.CTkFont(size=14)).pack(anchor="w", padx=5, pady=2)

self.date_entry = ctk.CTkEntry(date_frame, placeholder_text="YYYY-MM-DD")
self.date_entry.pack(fill="x", padx=5, pady=2)
```

#### 3. Добавить предпросмотр файла

```python
def _preview_file(self):
    """Показать предпросмотр последнего найденного файла"""
    if not self.results:
        return
    
    file_path = self.results[-1].path
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(1000)  # Первые 1000 символов
            
        preview_window = ctk.CTkToplevel(self)
        preview_window.title(f"Предпросмотр: {os.path.basename(file_path)}")
        preview_window.geometry("600x400")
        
        text_widget = ctk.CTkTextbox(preview_window)
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)
        text_widget.insert("1.0", content)
        
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
```

#### 4. Добавить историю поиска

```python
class FileSearcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.search_history = []  # НОВОЕ
        # ... остальной код
    
    def _save_search_to_history(self, params):
        """Сохраняет параметры поиска"""
        self.search_history.append({
            'timestamp': datetime.now(),
            'params': params,
            'results_count': len(self.results)
        })
        
        # Ограничение истории
        if len(self.search_history) > 10:
            self.search_history.pop(0)
```

---

## 🚀 Оптимизация для специфических задач

### 1. Поиск только в определенных директориях

Модифицируйте метод `search` в классе `FileSearchEngine`:

```python
# В начале метода search добавьте:
include_dirs = ['src', 'tests', 'docs']  # Только эти папки
exclude_dirs = ['node_modules', '.git', '__pycache__']  # Исключить

for root, dirs, files in os.walk(root_path):
    # Фильтрация директорий
    dirs[:] = [d for d in dirs 
               if d not in exclude_dirs 
               and (not include_dirs or d in include_dirs)]
```

### 2. Индексация для повторных поисков

```python
import pickle
from pathlib import Path

class SearchIndex:
    """Кэш для ускорения повторных поисков"""
    
    def __init__(self, cache_file=".search_cache.pkl"):
        self.cache_file = cache_file
        self.index = self._load_index()
    
    def _load_index(self):
        if Path(self.cache_file).exists():
            with open(self.cache_file, 'rb') as f:
                return pickle.load(f)
        return {}
    
    def save_index(self):
        with open(self.cache_file, 'wb') as f:
            pickle.dump(self.index, f)
    
    def index_directory(self, root_path):
        """Создает индекс всех файлов"""
        for root, dirs, files in os.walk(root_path):
            for file in files:
                file_path = os.path.join(root, file)
                stat = os.stat(file_path)
                
                self.index[file_path] = {
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'name': file
                }
```

### 3. GPU ускорение для regex (экспериментально)

Для очень больших объемов данных можно использовать CuPy:

```python
# Требует: pip install cupy-cuda11x
import cupy as cp

def gpu_regex_search(text_array, pattern):
    """Поиск по regex с использованием GPU"""
    # Это упрощенный пример
    # Реальная реализация требует специальной библиотеки
    try:
        import cudf  # GPU DataFrame
        # Конвертация в GPU DataFrame
        gpu_df = cudf.DataFrame({'text': text_array})
        # Поиск
        results = gpu_df[gpu_df['text'].str.contains(pattern)]
        return results.to_pandas()
    except ImportError:
        # Fallback на CPU
        return [text for text in text_array if re.search(pattern, text)]
```

---

## 📊 Статистика и аналитика

### Добавление статистики поиска

```python
def _show_statistics(self):
    """Показывает статистику найденных файлов"""
    if not self.results:
        return
    
    total_size = sum(r.size for r in self.results)
    avg_size = total_size / len(self.results)
    
    # Подсчет расширений
    extensions = {}
    for r in self.results:
        ext = os.path.splitext(r.path)[1]
        extensions[ext] = extensions.get(ext, 0) + 1
    
    # Создание окна статистики
    stats_window = ctk.CTkToplevel(self)
    stats_window.title("Статистика поиска")
    stats_window.geometry("400x300")
    
    stats_text = ctk.CTkTextbox(stats_window)
    stats_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    stats_text.insert("end", f"Всего файлов: {len(self.results)}\n")
    stats_text.insert("end", f"Общий размер: {self._format_size(total_size)}\n")
    stats_text.insert("end", f"Средний размер: {self._format_size(avg_size)}\n\n")
    stats_text.insert("end", "Расширения:\n")
    
    for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
        stats_text.insert("end", f"  {ext or '(нет)'}: {count}\n")
```

---

## 🔒 Безопасность

### Ограничение доступа к системным папкам

```python
RESTRICTED_PATHS = [
    r'C:\Windows\System32',
    r'C:\Windows\SysWOW64',
    r'C:\Program Files\WindowsApps'
]

def is_path_safe(path):
    """Проверяет, безопасен ли путь для доступа"""
    path = os.path.abspath(path)
    return not any(path.startswith(restricted) for restricted in RESTRICTED_PATHS)
```

### Ограничение размера файлов для содержимого

```python
MAX_FILE_SIZE_FOR_CONTENT = 50 * 1024 * 1024  # 50 МБ

def _search_in_file(self, file_path: str, pattern: re.Pattern) -> bool:
    if os.path.getsize(file_path) > MAX_FILE_SIZE_FOR_CONTENT:
        return False
    # ... остальной код
```

---

## 🎨 Кастомизация интерфейса

### Изменение цветовой схемы

```python
# В методе __init__
ctk.set_appearance_mode("dark")  # "light", "dark", "system"
ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"
```

### Создание собственной темы

Создайте файл `custom_theme.json`:

```json
{
  "CTk": {
    "fg_color": ["#1e1e1e", "#2d2d30"]
  },
  "CTkButton": {
    "fg_color": ["#007acc", "#005a9e"],
    "hover_color": ["#005a9e", "#004578"],
    "text_color": ["#ffffff", "#ffffff"]
  }
}
```

Загрузите в коде:

```python
ctk.set_default_color_theme("custom_theme.json")
```

---

## 📈 Профилирование производительности

### Измерение времени поиска

```python
import time

def _start_search(self):
    self.search_start_time = time.time()
    # ... остальной код

def _search_complete(self, results):
    elapsed = time.time() - self.search_start_time
    self.status_label.configure(
        text=f"Поиск завершен за {elapsed:.2f} сек! Найдено: {len(results)}"
    )
```

---

## 🛠️ Отладка

### Включение логирования

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='file_searcher.log'
)

logger = logging.getLogger(__name__)

# В коде:
logger.debug(f"Searching in {root_path}")
logger.info(f"Found {len(results)} files")
```

---

**Удачной разработки! 🚀**

