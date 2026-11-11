@echo off
chcp 65001 >nul
cd /d "%USERPROFILE%\daily-briefing"
echo Making posts for both accounts and posting now. 15-40 min.
py pc\run.py --slot now
echo.
echo Done. GitHub will post within a few minutes.
pause
