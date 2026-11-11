@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\daily-briefing\pc\register.ps1"
pause
