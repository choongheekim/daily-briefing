"""내레이션 음성 + 단어별 타이밍.

① 타입캐스트(TYPECAST_API_KEY 있으면): 한국어 감정 음성, 단어 타이밍 제공
② edge-tts(무료, 키 없을 때 자동): 단어 타이밍 제공
③ 둘 다 실패: 무음 + 글자 수로 추정한 타이밍 → 자막은 그대로 나옴

synth(text, out_base, channel, emotion) -> (오디오 경로, [{"text","start","end"}...], 길이초)
"""
import asyncio
import base64
import json
import os
import subprocess

import requests

TC_URL = "https://api.typecast.ai"
_voice_cache: dict = {}


def _duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── 타입캐스트 ────────────────────────────────────────────────
def _tc_headers():
    return {"X-API-KEY": os.environ["TYPECAST_API_KEY"], "Content-Type": "application/json"}


def typecast_voice(channel: str) -> str:
    """채널별 목소리: TYPECAST_VOICE_RIGHT/LEFT 지정값 → 없으면 중년 남성 목소리 자동 선택."""
    env = os.getenv(f"TYPECAST_VOICE_{channel.upper()}")
    if env:
        return env
    if channel in _voice_cache:
        return _voice_cache[channel]
    model = os.getenv("TYPECAST_MODEL", "ssfm-v31")
    r = requests.get(f"{TC_URL}/v3/voices", headers=_tc_headers(),
                     params={"model": model, "gender": "male", "voice_type": "original"}, timeout=30)
    r.raise_for_status()
    voices = r.json()

    def score(v):
        emos = {e for m in v.get("models", []) if m.get("version") == model for e in m.get("emotions", [])}
        s = 0
        s += 3 if v.get("age") == "middle_age" else 1 if v.get("age") == "young_adult" else 0
        s += 2 if "angry" in emos else 0
        s += 2 if "toneup" in emos else 0
        uc = " ".join(v.get("use_cases") or []).lower()
        s += 3 if any(k in uc for k in ("news", "뉴스", "announc", "documentary")) else 0
        return s
    voices.sort(key=score, reverse=True)
    # 두 채널이 다른 목소리를 쓰도록: right=1순위, left=2순위
    pick = voices[0 if channel == "right" else min(1, len(voices) - 1)]["voice_id"]
    _voice_cache[channel] = pick
    print(f"[tts] 타입캐스트 목소리 자동 선택({channel}): {pick}")
    return pick


def _typecast(text, out_base, channel, emotion):
    body = {
        "voice_id": typecast_voice(channel),
        "text": text,
        "model": os.getenv("TYPECAST_MODEL", "ssfm-v31"),
        "language": "kor",
        "prompt": {"emotion_type": "preset", "emotion_preset": emotion,
                   "emotion_intensity": float(os.getenv("TYPECAST_INTENSITY", "1.2"))},
        "output": {"audio_format": "wav", "audio_tempo": float(os.getenv("TYPECAST_TEMPO", "1.1")),
                   "target_lufs": -14},
    }
    r = requests.post(f"{TC_URL}/v1/text-to-speech/with-timestamps", headers=_tc_headers(),
                      params={"granularity": "word"}, data=json.dumps(body), timeout=120)
    if r.status_code == 400 and "emotion" in r.text:      # 목소리가 그 감정을 지원 안 하면 기본 감정으로
        body["prompt"] = {"emotion_type": "preset", "emotion_preset": "normal"}
        r = requests.post(f"{TC_URL}/v1/text-to-speech/with-timestamps", headers=_tc_headers(),
                          params={"granularity": "word"}, data=json.dumps(body), timeout=120)
    r.raise_for_status()
    d = r.json()
    path = out_base + ".wav"
    with open(path, "wb") as f:
        f.write(base64.b64decode(d["audio"]))
    words = [{"text": w["text"], "start": float(w["start"]), "end": float(w["end"])} for w in d.get("words") or []]
    return path, words, float(d.get("audio_duration") or _duration(path))


# ── edge-tts (무료) ───────────────────────────────────────────
# 무료 음성: 신형 멀티링구얼(Hyunsu)이 구형(InJoon)보다 훨씬 자연스러움
EDGE_VOICE = {"right": "ko-KR-HyunsuMultilingualNeural", "left": "ko-KR-HyunsuMultilingualNeural"}
EDGE_FALLBACK = "ko-KR-InJoonNeural"


def _edge(text, out_base, channel, emotion):
    import edge_tts
    voice = os.getenv(f"EDGE_VOICE_{channel.upper()}", EDGE_VOICE.get(channel, "ko-KR-InJoonNeural"))
    # 감정 대신 속도·높낮이로 톤 조절: 제목은 또렷하게, 한줄평은 빠르고 힘있게
    rate, pitch = {"toneup": ("+8%", "+4Hz"), "angry": ("+14%", "+2Hz")}.get(emotion, ("+5%", "+0Hz"))
    path = out_base + ".mp3"
    words = []

    async def go(v):
        words.clear()
        com = edge_tts.Communicate(text, v, rate=rate, pitch=pitch, boundary="WordBoundary")
        with open(path, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    s = ch["offset"] / 1e7
                    words.append({"text": ch["text"], "start": s, "end": s + ch["duration"] / 1e7})
    try:
        asyncio.run(go(voice))
        if os.path.getsize(path) < 1000:
            raise RuntimeError("빈 오디오")
    except Exception as e:
        print(f"[tts] {voice} 실패({e}) → {EDGE_FALLBACK}")
        asyncio.run(go(EDGE_FALLBACK))
    if os.path.getsize(path) < 1000:
        raise RuntimeError("edge-tts 빈 오디오")
    return path, words, _duration(path)


# ── 무음 + 추정 타이밍 ─────────────────────────────────────────
def _silent(text, out_base, secs_per_char=0.11):
    toks = text.split()
    t, words = 0.15, []
    for w in toks:
        d = max(0.18, len(w) * secs_per_char)
        words.append({"text": w, "start": t, "end": t + d})
        t += d + 0.06
    path = out_base + ".wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=44100:cl=stereo", "-t", f"{t + 0.2:.2f}", path], check=True)
    return path, words, t + 0.2


def synth(text: str, out_base: str, channel: str, emotion: str = "normal"):
    text = " ".join(text.split())
    if os.getenv("REEL_NARRATION", "1") == "1":
        if os.getenv("TYPECAST_API_KEY"):
            try:
                return _typecast(text, out_base, channel, emotion)
            except Exception as e:
                print(f"[tts] 타입캐스트 실패 → 무료 음성으로: {e}")
        try:
            return _edge(text, out_base, channel, emotion)
        except Exception as e:
            print(f"[tts] 무료 음성 실패 → 무음 자막: {e}")
    return _silent(text, out_base)
