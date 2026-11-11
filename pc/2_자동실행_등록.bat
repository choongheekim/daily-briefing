@echo off
chcp 65001 >nul
cd /d "%USERPROFILE%\daily-briefing"
git pull -q
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\daily-briefing\pc\register.ps1"
pause
