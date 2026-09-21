@echo off
title Telegram Video Downloader Bot
color 0a
echo ======================================================
echo       DANG KHOI DONG TELEGRAM BOT TAI VIDEO
echo ======================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.8+ tu python.org va tich chon "Add Python to PATH".
    pause
    exit /b 1
)

:: Kiem tra thu vien
python -c "import telebot, dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo Dang cai dat thu vien pyTelegramBotAPI...
    pip install pyTelegramBotAPI python-dotenv
)

python bot.py

pause
