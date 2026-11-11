@echo off
chcp 65001 >nul
cd /d "%USERPROFILE%\daily-briefing"
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\daily-briefing\pc\unregister.ps1"
pause
