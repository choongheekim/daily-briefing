@echo off
chcp 65001 >nul
cd /d "%USERPROFILE%\daily-briefing"
echo Writing extra post with Claude Code... (5-10 min)
py pc\write.py --extra
echo.
echo Done. GitHub will post in about 10 minutes. Log: %USERPROFILE%\daily-briefing-logs
pause
