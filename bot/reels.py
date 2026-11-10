"""릴스 영상(1080x1920, 9:16) 생성.

구성: 인트로(훅) → 이슈 5개(사진 배경 + 제목 + 릴스용 한줄평) → 아웃트로(팔로우)
내레이션: edge-tts 무료 한국어 음성 (실패하면 자막만 있는 무음 영상으로 자동 전환)
배경음악: reels_bgm.mp3 파일을 저장소 루트에 넣으면 낮은 볼륨으로 깔림(없으면 생략)
움직임: 각 장면을 천천히 확대(켄 번스 효과)
"""
import asyncio
import os
import subprocess
from datetime import datetime

from PIL import Image, ImageDraw

from bot import render as R

RW, RH = 1080, 1920
FPS = 30
VOICE = {"right": os.getenv("REEL_VOICE_RIGHT", "ko-KR-InJoonNeural"),
         "left": os.getenv("REEL_VOICE_LEFT", "ko-KR-InJoonNeural")}
# 릴스 화면 하단(캡션·버튼)과 오른쪽(좋아요 버튼)은 가려지므로 이 안쪽에만 글자 배치
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 230, 1540, 940


def _bg(img, photo):
    path, credit, kind = photo
    ph = Image.open(path).convert("RGB")
    sc = max(RW / ph.width, RH / ph.height)
    ph = ph.resize((int(ph.width * sc) + 1, int(ph.height * sc) + 1), Image.LANCZOS)
    x = (ph.width - RW) // 2
    y = int((ph.height - RH) * (0.15 if kind == "person" else 0.4))
    img.paste(ph.crop((x, y, x + RW, y + RH)), (0, 0))
    grad = Image.new("L", (1, RH))
    for i in range(RH):
        t = i / RH
        if kind in ("person", "event"):
            a = 70 if t < 0.10 else 20 if t < 0.32 else int(20 + 205 * min(1, (t - 0.32) / 0.2))
        else:
            a = int(150 + 75 * t)
        grad.putpixel((0, i), min(a, 228))
    img.paste(Image.new("RGB", (RW, RH), R.BG), (0, 0), grad.resize((RW, RH)))
    d = ImageDraw.Draw(img)
    if credit:
        f = R.font(22, "regular")
        d.text((RW - 30 - d.textlength(credit, font=f), 120), credit, font=f, fill=(220, 220, 225),
                stroke_width=1, stroke_fill=(0, 0, 0))


def _frame(photo=None):
    img = Image.new("RGB", (RW, RH), R.BG)
    if photo:
        _bg(img, photo)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, RW, 16], fill=R.ACCENT)
    return img, d


def _intro(content, photo):
    img, d = _frame(photo)
    now = datetime.now(R.KST)
    d.text((70, SAFE_TOP), f"{now:%Y.%m.%d} ({'월화수목금토일'[now.weekday()]})",
           font=R.font(44, "bold"), fill=R.FG, stroke_width=2, stroke_fill=(0, 0, 0))
    lab_f = R.font(50, "title")
    lw = d.textlength(R.LABEL, font=lab_f)
    d.rectangle([70, SAFE_TOP + 80, 70 + lw + 44, SAFE_TOP + 170], fill=R.ACCENT)
    d.text((92, SAFE_TOP + 92), R.LABEL, font=lab_f, fill=R.FG)
    tf = R.font(128, "title")
    lines = R.wrap(d, R.title_text(content.get("reel_hook") or content["cover_title"]), tf, SAFE_RIGHT - 70)[:4]
    y = 820 - len(lines) * 75
    for ln in lines:
        R.title_draw(d, (70, y), ln, tf, R.YELLOW)
        y += 150
    y += 40
    lf = R.font(44, "bold")
    for i, s in enumerate(content["stories"], 1):
        if y > SAFE_BOTTOM - 60:
            break
        t = R.wrap(d, s["headline"], lf, SAFE_RIGHT - 160)[0]
        d.text((70, y), f"{i:02d}", font=lf, fill=R.ACCENT, stroke_width=2, stroke_fill=(0, 0, 0))
        d.text((150, y), t, font=lf, fill=R.FG, stroke_width=2, stroke_fill=(0, 0, 0))
        y += 66
    return img


def _story(s, num, photo):
    img, d = _frame(photo)
    person_photo = bool(photo) and photo[2] in ("person", "event")
    nf = R.font(150, "title")
    d.text((70, SAFE_TOP - 20), f"{num:02d}", font=nf, fill=R.ACCENT)
    tag_f = R.font(40, "bold")
    tx = int(70 + d.textlength(f"{num:02d}", font=nf) + 30)
    tw = d.textlength(s.get("tag", "정치"), font=tag_f)
    d.rounded_rectangle([tx, SAFE_TOP + 45, tx + tw + 48, SAFE_TOP + 113], radius=34,
                        fill=(0, 0, 0), outline=R.FG, width=3)
    d.text((tx + 24, SAFE_TOP + 50), s.get("tag", "정치"), font=tag_f, fill=R.FG)

    y = 760 if person_photo else 600
    if person_photo and s.get("person") and photo[2] == "person":
        d.text((70, y - 66), s["person"], font=R.font(42, "bold"), fill=R.FG,
               stroke_width=3, stroke_fill=(0, 0, 0))
    hf = R.font(96, "title")
    for ln in R.wrap(d, R.title_text(s["headline"]), hf, SAFE_RIGHT - 70)[:2]:
        R.title_draw(d, (70, y), ln, hf, R.YELLOW)
        y += 118

    # 릴스 한줄평 박스 (주인공) — 글자 크기를 줄여가며 전부 넣기
    cm = s.get("reel_comment") or s.get("comment") or ""
    box_top = y + 50
    room = SAFE_BOTTOM - box_top - 40
    for sz in (62, 58, 54, 50, 46, 42, 38):
        cf = R.font(sz, "black")
        lines = R.wrap(d, cm, cf, SAFE_RIGHT - 70 - 70)
        lh = int(sz * 1.45)
        bh = 100 + len(lines) * lh
        if bh <= room:
            break
    d.rounded_rectangle([50, box_top, SAFE_RIGHT + 20, box_top + bh], radius=22,
                        fill=tuple(int(c * 0.25 + 15) for c in R.ACCENT))
    d.rectangle([50, box_top, 64, box_top + bh], fill=R.ACCENT)
    chip_f = R.font(34, "black")
    cw = d.textlength("한줄평", font=chip_f)
    d.rounded_rectangle([90, box_top + 24, 90 + cw + 30, box_top + 76], radius=12, fill=R.ACCENT)
    d.text((105, box_top + 28), "한줄평", font=chip_f, fill=R.FG)
    ty = box_top + 96
    for ln in lines:
        d.text((90, ty), ln, font=cf, fill=R.FG)
        ty += lh
    src = "출처: " + ", ".join(s.get("sources", [])[:4])
    d.text((70, min(box_top + bh + 24, SAFE_BOTTOM + 10)), src, font=R.font(30, "regular"),
           fill=(200, 200, 208), stroke_width=1, stroke_fill=(0, 0, 0))
    return img


def _outro(photo):
    img, d = _frame(photo)
    f1 = R.font(120, "title")
    y = 640
    for ln in ["매일 아침 7시", "정치 핫이슈", "5개만 콕"]:
        R.title_draw(d, (70, y), ln, f1, R.YELLOW if ln == "정치 핫이슈" else R.FG)
        y += 150
    d.text((70, y + 50), f"팔로우 {R.ACCOUNT}", font=R.font(64, "black"), fill=R.ACCENT,
           stroke_width=3, stroke_fill=(255, 255, 255))
    note = "※ 언론 보도를 AI가 요약·논평했습니다. 한줄평은 이 계정의 의견입니다."
    yy = y + 190
    for ln in R.wrap(d, note, R.font(32, "regular"), SAFE_RIGHT - 70):
        d.text((70, yy), ln, font=R.font(32, "regular"), fill=(210, 210, 215),
               stroke_width=1, stroke_fill=(0, 0, 0))
        yy += 48
    return img


def _tts(text, out, voice):
    """edge-tts로 음성 생성. 실패하면 None."""
    if os.getenv("REEL_NARRATION", "1") != "1":
        return None
    try:
        import edge_tts

        async def go():
            await edge_tts.Communicate(text, voice, rate="+15%").save(out)
        asyncio.run(go())
        return out if os.path.getsize(out) > 1000 else None
    except Exception as e:
        print(f"[reels] 음성 생성 실패 → 무음 진행: {e}")
        return None


def _dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _segment(png, audio, seconds, out):
    frames = int(seconds * FPS)
    vf = (f"scale=1296:2304,zoompan=z='min(zoom+0.0004,1.07)':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d={frames}:s={RW}x{RH}:fps={FPS},format=yuv420p")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", png]
    if audio:
        cmd += ["-i", audio]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-filter_complex", f"[0:v]{vf}[v];[1:a]aresample=44100,apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{seconds:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", out]
    subprocess.run(cmd, check=True)


def build_reel(content, channel_id, out_dir, pick) -> str:
    """content: 요약 결과, pick(person, tag, salt, queries) → 배경 사진 선택 함수."""
    work = os.path.join(out_dir, "_reel")
    os.makedirs(work, exist_ok=True)
    voice = VOICE.get(channel_id, "ko-KR-InJoonNeural")
    stories = content["stories"]
    scenes = [(_intro(content, pick(content.get("cover_person"), stories[0].get("tag"), 11,
                                    stories[0].get("photo_queries"))),
               content.get("reel_hook") or content["cover_title"], 3.0)]
    for i, s in enumerate(stories, 1):
        say = f"{i}번. {s['headline']}. {s.get('reel_comment') or s.get('comment', '')}"
        scenes.append((_story(s, i, pick(s.get("person"), s.get("tag"), 20 + i, s.get("photo_queries"))),
                       say, 7.0))
    scenes.append((_outro(pick(None, None, 30)),
                   f"매일 아침 7시, 정치 핫이슈 다섯 개. 팔로우하고 받아보세요.", 3.0))

    parts = []
    for k, (img, say, min_s) in enumerate(scenes):
        png = os.path.join(work, f"s{k:02d}.png")
        img.save(png)
        audio = _tts(R.clean_text(say).replace('"', "").replace("'", ""), os.path.join(work, f"s{k:02d}.mp3"), voice)
        secs = max(min_s, _dur(audio) + 0.5) if audio else min_s
        seg = os.path.join(work, f"s{k:02d}.mp4")
        _segment(png, audio, secs, seg)
        parts.append(seg)

    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    joined = os.path.join(work, "joined.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", joined], check=True)

    out = os.path.join(out_dir, "reel.mp4")
    bgm = "reels_bgm.mp3"
    if os.path.exists(bgm):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-stream_loop", "-1", "-i", bgm,
                        "-filter_complex", "[1:a]volume=0.12[b];[0:a][b]amix=inputs=2:duration=first[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", out],
                       check=True)
    else:
        os.replace(joined, out)
    print(f"[reels] {out} ({_dur(out):.1f}초, {os.path.getsize(out) / 1e6:.1f}MB)")
    return out


def reel_caption(content) -> str:
    lines = [content.get("reel_hook") or content["caption_hook"], ""]
    for i, s in enumerate(content["stories"], 1):
        lines.append(f"{i}. {s['headline']}")
    lines += ["", "※ 언론 보도를 AI가 요약·논평했습니다. 한줄평은 이 계정의 의견입니다.", "",
              " ".join(content.get("hashtags", [])[:10] + ["#릴스", "#정치뉴스"])]
    return "\n".join(lines)[:2200]
