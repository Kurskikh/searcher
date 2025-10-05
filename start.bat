@echo off
chcp 65001 >nul
echo ========================================
echo   Мощный Файловый Поисковик
echo ========================================
echo.

REM Проверка установки Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [✓] Python найден
echo.

REM Проверка и установка зависимостей
echo Проверка зависимостей...
pip show customtkinter >nul 2>&1
if errorlevel 1 (
    echo [!] Установка зависимостей...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить зависимости
        pause
        exit /b 1
    )
) else (
    echo [✓] Зависимости установлены
)

echo.
echo ========================================
echo   Запуск приложения...
echo ========================================
echo.

REM Запуск приложения
python file_searcher.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой
    pause
    exit /b 1
)

exit /b 0

