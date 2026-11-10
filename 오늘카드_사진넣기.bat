@echo off
chcp 65001 > nul
cd /d %~dp0
pip install -q -r requirements.txt
python rerender.py --channel right --date 2026-11-10
python rerender.py --channel left  --date 2026-11-10
echo.
echo 완료! posts\right\2026-11-10 , posts\left\2026-11-10 폴더를 확인하세요.
pause
