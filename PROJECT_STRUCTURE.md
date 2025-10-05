# 📁 Структура проекта

Профессиональная организация файлов Python проекта.

## 📂 Структура директорий

```
searcher/
├── 📁 src/                         # Исходный код приложения
│   ├── __init__.py                 # Инициализация пакета
│   ├── file_searcher.py            # Главное приложение с GUI
│   └── gpu_search_engine.py        # Модуль GPU ускорения
│
├── 📁 docs/                        # Документация проекта
│   ├── ADVANCED.md                 # Продвинутые возможности
│   ├── QUICK_START.md              # Быстрый старт
│   ├── START_HERE.md               # Подробное руководство
│   ├── GPU_SETUP.md                # Настройка GPU
│   └── GPU_QUICKSTART.txt          # Краткая инструкция по GPU
│
├── 📁 scripts/                     # Скрипты для управления проектом
│   ├── install.bat                 # Установка зависимостей
│   ├── install_gpu.bat             # Установка GPU компонентов
│   └── start.bat                   # Запуск приложения (из папки scripts)
│
├── 📁 assets/                      # Ресурсы (изображения, иконки)
│   └── icon.png                    # Иконка приложения
│
├── 📁 config/                      # Конфигурационные файлы
│   └── search_presets.json         # Сохраненные пресеты поиска
│
├── 📁 build/                       # Файлы для сборки
│   ├── FileSearcher.spec           # PyInstaller спецификация (CPU)
│   └── FileSearcher_GPU.spec       # PyInstaller спецификация (GPU)
│
├── 📁 tests/                       # Юнит-тесты (будущее)
│   └── (пока пусто)
│
├── 📄 .gitignore                   # Исключения для Git
├── 📄 README.md                    # Главная документация
├── 📄 CHANGELOG.md                 # История изменений
├── 📄 PROJECT_STRUCTURE.md         # Этот файл
├── 📄 requirements.txt             # Python зависимости
├── 📄 start.bat                    # Запуск из корня (рекомендуется)
├── 📄 cuda_dlls_found.txt          # Список найденных CUDA DLL
└── 📄 file_searcher_CPUsearcher.py # Старая версия (только CPU)
```

## 🚀 Быстрый старт

### Из корня проекта (рекомендуется):
```bash
start.bat
```

### Из папки scripts:
```bash
cd scripts
start.bat
```

### Прямой запуск Python:
```bash
python -m src.file_searcher
```

## 📦 Установка зависимостей

### Основные зависимости:
```bash
pip install -r requirements.txt
```

### GPU ускорение (опционально):
```bash
# Из корня проекта
cd scripts
install_gpu.bat
```

## 🛠️ Разработка

### Структура кода

#### `src/file_searcher.py`
- Класс `FileSearchEngine` - ядро поисковой системы
- Класс `FileSearcherApp` - GUI приложение
- Многопоточный поиск с ThreadPoolExecutor
- Интеграция с GPU движком

#### `src/gpu_search_engine.py`
- Класс `GPUPatternMatcher` - GPU ускорение regex
- Класс `HybridSearchEngine` - гибридный CPU/GPU движок
- CUDA kernels для параллельного поиска
- Автоматический выбор CPU/GPU в зависимости от размера файла

### Добавление новых функций

1. Код приложения → `src/`
2. Документация → `docs/`
3. Скрипты → `scripts/`
4. Ресурсы → `assets/`
5. Конфиги → `config/`

### Импорты

Все импорты используют относительные пути от `src/`:

```python
# В file_searcher.py
from gpu_search_engine import HybridSearchEngine, GPU_AVAILABLE

# Путь к assets
project_root = os.path.dirname(os.path.dirname(__file__))
icon_path = os.path.join(project_root, "assets", "icon.png")
```

## 🏗️ Сборка исполняемого файла

### CPU версия:
```bash
pyinstaller build/FileSearcher.spec
```

### GPU версия:
```bash
pyinstaller build/FileSearcher_GPU.spec
```

Результат сборки появится в папке `dist/`.

## 📝 Документация

- **README.md** - основная информация о проекте
- **CHANGELOG.md** - история изменений
- **docs/START_HERE.md** - подробное руководство для начинающих
- **docs/QUICK_START.md** - быстрый старт
- **docs/ADVANCED.md** - продвинутые возможности
- **docs/GPU_SETUP.md** - настройка GPU ускорения
- **PROJECT_STRUCTURE.md** - структура проекта (этот файл)

## 🔧 Конфигурация

### `.gitignore`
Исключает из Git:
- `__pycache__/`, `*.pyc` - Python cache
- `venv/`, `env/` - виртуальные окружения
- `build/`, `dist/` - артефакты сборки
- `*.log`, `*.tmp` - временные файлы

### `requirements.txt`
Основные зависимости:
- `customtkinter` - современный GUI
- `Pillow` - работа с изображениями

Опциональные (GPU):
- `cupy-cuda11x` - NumPy для GPU
- `numba` - JIT компиляция CUDA

## 🎯 Лучшие практики

✅ **DO:**
- Используйте `start.bat` из корня для запуска
- Документируйте новые функции в `docs/`
- Следуйте структуре папок
- Используйте относительные импорты

❌ **DON'T:**
- Не храните временные файлы в репозитории
- Не смешивайте код и документацию в одной папке
- Не используйте абсолютные пути

## 📊 Статистика проекта

- **Языки**: Python 3.8+
- **GUI**: CustomTkinter
- **Архитектура**: Hybrid CPU/GPU
- **Потоки**: Многопоточный поиск
- **GPU**: CUDA ускорение (опционально)

## 🔗 Полезные ссылки

- [GitHub Repository](https://github.com/Kurskikh/searcher)
- [Python Documentation](https://docs.python.org/3/)
- [CustomTkinter Docs](https://customtkinter.tomschimansky.com/)
- [CUDA Documentation](https://docs.nvidia.com/cuda/)
