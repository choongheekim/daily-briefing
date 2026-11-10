@echo off
chcp 65001 > nul
cd /d %~dp0
pip install -q requests
echo 계정마다 한 번씩 실행하세요. 토큰은 화면에 남지 않게 붙여넣고 Enter.
python find_ig_ids.py
echo.
pause
