@echo off
title TLOU 3D Asset Server (HD Textures)
cd /d "%~dp0"
echo ========================================================
echo   TLOU PS4 3D Asset Viewer Local Server
echo   Serves HD textures (512px - 2048px) to viewer.html
echo ========================================================
echo.
python serve.py
if errorlevel 1 (
    echo.
    echo [ERROR] Python failed to start serve.py.
    pause
)
