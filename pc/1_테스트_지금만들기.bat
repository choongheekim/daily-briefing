@echo off
chcp 65001 >nul
cd /d "%USERPROFILE%\daily-briefing"
echo Making TEST posts for both accounts (not posted). 15-40 min.
git pull -q
py pc\run.py --slot now --test
echo.
echo Done. Folders with the cards will open.
pause
