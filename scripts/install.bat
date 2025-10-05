@echo off
chcp 65001 >nul
echo ========================================
echo   Установка Файлового Поисковика
echo ========================================
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не установлен!
    echo.
    echo Пожалуйста, установите Python 3.8 или новее:
    echo https://www.python.org/downloads/
    echo.
    echo ВАЖНО: При установке отметьте "Add Python to PATH"
    pause
    exit /b 1
)

echo [✓] Python установлен
python --version
echo.

REM Обновление pip
echo Обновление pip...
python -m pip install --upgrade pip
echo.

REM Установка зависимостей
echo Установка зависимостей...
echo.
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости
    echo Попробуйте выполнить вручную:
    echo   pip install customtkinter pillow
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Установка завершена успешно!
echo ========================================
echo.
echo Для запуска используйте:
echo   - Двойной клик на start.bat
echo   - Или: python file_searcher.py
echo.
pause

