@echo off
chcp 65001 >nul
echo ========================================
echo   Установка GPU ускорения (CUDA)
echo ========================================
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    pause
    exit /b 1
)

echo [✓] Python найден
python --version
echo.

REM Проверка NVIDIA GPU
echo Проверка NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] NVIDIA GPU или драйверы не найдены!
    echo.
    echo Убедитесь что:
    echo 1. У вас установлена видеокарта NVIDIA
    echo 2. Установлены последние драйверы NVIDIA
    echo 3. CUDA Toolkit установлен
    echo.
    echo Скачать CUDA: https://developer.nvidia.com/cuda-downloads
    pause
    exit /b 1
)

echo [✓] NVIDIA GPU найдена
echo.

REM Получаем версию CUDA
echo Определение версии CUDA...
nvidia-smi | findstr "CUDA Version"
echo.

REM Спрашиваем пользователя
echo Какая версия CUDA установлена?
echo.
echo 1) CUDA 12.x (рекомендуется для новых GPU)
echo 2) CUDA 11.x
echo 3) Другая версия (ручная установка)
echo 4) Отмена
echo.
set /p cuda_choice="Введите номер (1-4): "

if "%cuda_choice%"=="1" (
    set CUPY_PACKAGE=cupy-cuda12x
    set CUDA_VER=12.x
) else if "%cuda_choice%"=="2" (
    set CUPY_PACKAGE=cupy-cuda11x
    set CUDA_VER=11.x
) else if "%cuda_choice%"=="3" (
    echo.
    echo Для ручной установки используйте:
    echo   pip install cupy-cuda118  ^(для CUDA 11.8^)
    echo   pip install cupy-cuda117  ^(для CUDA 11.7^)
    echo   pip install cupy-cuda116  ^(для CUDA 11.6^)
    echo.
    echo Полный список: https://docs.cupy.dev/en/stable/install.html
    pause
    exit /b 0
) else (
    echo Установка отменена
    exit /b 0
)

echo.
echo ========================================
echo   Установка CuPy для CUDA %CUDA_VER%
echo ========================================
echo.

pip install %CUPY_PACKAGE% numba

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить GPU зависимости
    echo.
    echo Попробуйте:
    echo 1. Установите CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
    echo 2. Обновите pip: python -m pip install --upgrade pip
    echo 3. Установите Visual Studio Build Tools
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Проверка установки
echo ========================================
echo.

REM Тестируем GPU
python -c "import cupy as cp; import numba.cuda as cuda; print('✓ CuPy версия:', cp.__version__); print('✓ CUDA доступна:', cuda.is_available()); print('✓ GPU:', cuda.get_current_device().name.decode() if cuda.is_available() else 'Не найдена')" 2>nul

if errorlevel 1 (
    echo [ОШИБКА] GPU не работает корректно
    echo.
    echo Возможные причины:
    echo 1. Несоответствие версии CuPy и CUDA
    echo 2. Устаревшие драйверы NVIDIA
    echo 3. CUDA Toolkit не установлен
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Тестирование GPU Search Engine
echo ========================================
echo.

python gpu_search_engine.py

echo.
echo ========================================
echo   Установка завершена успешно!
echo ========================================
echo.
echo GPU ускорение готово к использованию!
echo.
echo В приложении включите опцию:
echo   🚀 GPU ускорение (CUDA)
echo   ☑ Использовать GPU для поиска в содержимом
echo.
echo Подробности: GPU_SETUP.md
echo.
pause

