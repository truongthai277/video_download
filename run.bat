@echo off
title Video Downloader Web Server
color 0b
echo ======================================================
echo       DANG KHOI DONG VIDEO DOWNLOADER WEB APP
echo ======================================================
echo.

:: Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.8+ tu python.org va tich chon "Add Python to PATH".
    pause
    exit /b 1
)

:: Kiem tra va cai dat thu vien neu thieu
echo [1/2] Dang kiem tra thu vien (yt-dlp, flask)...
python -c "import yt_dlp, flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo Dang cai dat cac goi can thiet...
    pip install -r requirements.txt
)

:: Mo trinh duyet sau 2 giay
start "" "http://localhost:5000"

echo [2/2] Dang khoi dong may chu tai: http://localhost:5000
echo Nhan Ctrl + C de dung may chu.
echo.
python app.py

pause
