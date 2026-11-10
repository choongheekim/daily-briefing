"""윈도우 작업 스케줄러에 '매일 자동 실행' 등록.

사용법: python schedule_setup.py 08:30      (시간 생략 시 08:30)
삭제:   python schedule_setup.py --remove
"""
import os
import subprocess
import sys

NAME = "DailyBriefingBot"
here = os.path.dirname(os.path.abspath(__file__))
py = sys.executable.replace("python.exe", "pythonw.exe")  # 창 안 뜨게
if not os.path.exists(py):
    py = sys.executable

if "--remove" in sys.argv:
    subprocess.run(["schtasks", "/Delete", "/TN", NAME, "/F"])
    sys.exit()

at = next((a for a in sys.argv[1:] if ":" in a), "08:30")
cmd = f'"{py}" "{os.path.join(here, "run_local.py")}"'
r = subprocess.run(["schtasks", "/Create", "/TN", NAME, "/TR", cmd, "/SC", "DAILY", "/ST", at, "/F"])
if r.returncode == 0:
    print(f"등록 완료: 매일 {at} 실행 (PC가 켜져 있고 로그인 상태여야 함)")
    print("결과는 run_log.txt 에 기록됩니다.")
