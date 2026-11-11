"""카드 이미지로 릴스(1080×1920) 만들기 — GitHub Actions에서 실행(ffmpeg, 무료 edge-tts).

카드 한 장 = 한 장면: 흐린 카드 배경 + 가운데 카드(천천히 확대) + 그 카드 내레이션.
첫 장면은 hook 문장을 먼저 읽고, 마지막 장면은 한줄평(계정 의견)을 읽는다.
"""
import asyncio
import json
import os
import subprocess
import sys

from PIL import Image, ImageFilter

RW, RH, FPS = 1080, 1920, 30
VOICES = ["ko-KR-HyunsuMultilingualNeural", "ko-KR-InJoonNeural"]


def _tts(text: str, out: str) -> float:
    """edge-tts로 음성 파일 → 길이(초). 실패하면 무음."""
    text = (text or "").replace("**", "").strip()
    if text:
        try:
            import edge_tts
            for v in VOICES:
                try:
                    asyncio.run(edge_tts.Communicate(text, v, rate="+8%").save(out))
                    if os.path.getsize(out) > 1000:
                        break
                except Exception:
                    continue
        except ImportError:
            pass
    if not os.path.exists(out) or os.path.getsize(out) < 1000:
        dur = max(3.0, len(text) * 0.12)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", f"{dur:.2f}", out], check=True)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 3)


def _frame(card: str, out: str):
    im = Image.open(card).convert("RGB")
    bg = im.resize((RW, int(im.height * RW / im.width))).resize((int(RH * im.width / im.height), RH))
    bg = bg.crop(((bg.width - RW) // 2, 0, (bg.width - RW) // 2 + RW, RH)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (RW, RH), (0, 0, 0)), 0.45)
    bg.paste(im.resize((RW, 1350)), (0, 230))          # 위 230px은 인스타 화면 글자 영역
    bg.save(out, quality=95)


def build(cards: list[str], script: dict, out_mp4: str, work: str) -> str:
    os.makedirs(work, exist_ok=True)
    lines = list(script.get("lines", []))[: len(cards)]
    lines += [""] * (len(cards) - len(lines))
    if script.get("hook"):
        lines[0] = f"{script['hook']} {lines[0]}".strip()
    parts = []
    for i, (card, text) in enumerate(zip(cards, lines), 1):
        fr, au, seg = (os.path.join(work, f"{i:02d}.{x}") for x in ("jpg", "mp3", "mp4"))
        _frame(card, fr)
        dur = _tts(text, au) + 0.6
        n = int(dur * FPS)
        zoom = f"zoompan=z='min(1+0.04*on/{n},1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={RW}x{RH}:fps={FPS}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", fr, "-i", au,
                        "-filter_complex", f"[0:v]scale=2160:-1,{zoom},format=yuv420p[v];[1:a]apad,aresample=44100[a]",
                        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-ac", "2", seg], check=True)
        parts.append(seg)
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", "-movflags", "+faststart", out_mp4], check=True)
    return out_mp4


if __name__ == "__main__":
    d = sys.argv[1]
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    cards = sorted(p for p in os.listdir(d) if p[:2].isdigit() and p.endswith(".jpg"))
    print(build([os.path.join(d, c) for c in cards], meta["reel_script"], os.path.join(d, "reel.mp4"), "/tmp/reel_work"))
