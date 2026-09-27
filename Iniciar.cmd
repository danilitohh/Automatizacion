@echo off
setlocal
cd /d "%~dp0"
title UTEL QA - Instalacion e inicio

rem Prepara Python, Node.js, Chromium, Electron y los recursos antes de abrir la app.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1" -Mode desktop -Launch
set "EXIT_CODE=%ERRORLEVEL%"

rem Mantiene visible el mensaje de error cuando se inicia con doble clic.
if not "%EXIT_CODE%"=="0" (
    echo.
    echo No se pudo iniciar UTEL QA. Revisa el mensaje anterior.
    pause
)

exit /b %EXIT_CODE%
