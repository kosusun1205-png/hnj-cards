"""오늘의 띠별 운세 → 인스타 릴스용 세로 영상(1080x1920, 약 13초) 생성.

장면: 오프닝 → TOP3(3위·2위·1위) → 오늘 조심할 띠 → 프로필 링크 안내
배경음은 저작권 걱정 없도록 코드로 합성한 잔잔한 화음.
"""
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave

from card import render_png, _esc, log

W, H, FPS, FADE = 1080, 1920, 30, 0.3
WEEK = "월화수목금토일"

CSS = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700;900&display=block" rel="stylesheet">
<style>
:root{--or:#F0641E;--cream:#FBF6EF;--ink:#2B2320;--mute:#8A7A6E;}
html,body{margin:0;padding:0;}
body{width:1080px;height:1920px;overflow:hidden;font-family:'Noto Sans KR',sans-serif;color:var(--ink);
     display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;}
.brand{position:absolute;top:150px;left:0;right:0;font-family:'Noto Serif KR',serif;font-weight:900;
       font-size:36px;letter-spacing:6px;}
.date{position:absolute;bottom:170px;left:0;right:0;font-size:34px;font-weight:500;opacity:.7;}
.circle{width:340px;height:340px;border-radius:50%;display:flex;flex-direction:column;
        align-items:center;justify-content:center;color:#fff;}
.hz{font-family:'Noto Serif KR',serif;font-weight:900;font-size:150px;line-height:1;}
.nm{font-size:44px;font-weight:700;margin-top:8px;}
.rank{font-size:64px;font-weight:900;margin-bottom:56px;letter-spacing:-1px;}
.stars{font-size:62px;color:var(--or);letter-spacing:8px;margin-top:64px;}
.line{font-size:68px;font-weight:900;line-height:1.35;letter-spacing:-2px;margin-top:40px;padding:0 80px;word-break:keep-all;}
</style></head><body>"""


def _scene_hook(today):
    return CSS + f"""<style>body{{background:var(--ink);color:#fff;}}</style>
<div class="brand" style="color:var(--or)">H&amp;J 사주상담소</div>
<div style="font-size:60px;font-weight:500;color:#CDBFB4;">{today.month}월 {today.day}일 {WEEK[today.weekday()]}요일</div>
<div style="font-size:150px;font-weight:900;line-height:1.15;letter-spacing:-5px;margin-top:40px;">오늘<br>운 좋은 띠</div>
<div style="font-size:230px;font-weight:900;color:#FF8A4C;letter-spacing:-6px;line-height:1.1;">TOP 3</div>
<div style="font-size:54px;font-weight:700;margin-top:60px;color:#CDBFB4;">내 띠는 있을까?</div>
</body></html>"""


def _scene_rank(today, rank, row, line, color, bg):
    stars = "★" * row["star"] + "☆" * (5 - row["star"])
    return CSS + f"""<style>body{{background:{bg};}}</style>
<div class="brand" style="color:var(--or)">H&amp;J 사주상담소</div>
<div class="rank" style="color:{color}">{rank}</div>
<div class="circle" style="background:{color}"><span class="hz">{row['zhi']}</span><span class="nm">{row['tti']}띠</span></div>
<div class="stars">{stars}</div>
<div class="line">{_esc(line)}</div>
<div class="date">{today.month}월 {today.day}일 오늘의 띠별 운세</div>
</body></html>"""


def _scene_cta():
    return CSS + """<style>body{background:var(--or);color:#fff;}</style>
<div class="brand">H&amp;J 사주상담소</div>
<div style="font-size:112px;font-weight:900;line-height:1.25;letter-spacing:-4px;">같은 띠라도<br>사주는<br>다 달라요</div>
<div style="font-size:52px;font-weight:500;line-height:1.6;margin-top:90px;color:#FFE3D3;">태어난 해·달·날·시로 보는<br>나만의 매일 운세</div>
<div style="font-size:62px;font-weight:900;margin-top:90px;background:#fff;color:var(--or);
     padding:26px 60px;border-radius:999px;">프로필 링크에서 확인</div>
</body></html>"""


def plan(data):
    """(장면 HTML, 길이초) 목록."""
    from datetime import date
    today = date.fromisoformat(data["date"])
    rows, lines = data["rows"], data["copy"]["lines"]
    # 별점 높은 순, 동점이면 관계의 힘(육합 > 삼합 > 같은 기운 > 생 > 재 > …) 순
    prio = ["육합", "삼합", "같은 기운", "생(도움 받음)", "재(내가 다스림)", "평", "설(내가 베풂)"]
    rk = lambda i: (-rows[i]["star"], prio.index(rows[i]["rel"]) if rows[i]["rel"] in prio else 99, i)
    idx = sorted(range(12), key=rk)
    top3 = idx[:3]
    worst = min(range(12), key=lambda i: rows[i]["star"])
    scenes = [(_scene_hook(today), 2.6)]
    for rank, i in zip(["3위", "2위", "1위"], [top3[2], top3[1], top3[0]]):
        scenes.append((_scene_rank(today, rank, rows[i], lines[i], "#F0641E", "#FBF6EF"), 2.4))
    scenes.append((_scene_rank(today, "오늘 조심할 띠", rows[worst], lines[worst],
                               "#3D5A80", "#EEF1F5"), 2.4))
    scenes.append((_scene_cta(), 3.0))
    return scenes, [rows[i]["tti"] for i in top3], rows[worst]["tti"]


def _ffmpeg():
    exe = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    return exe


def _bgm(path, seconds, sr=44100):
    """C - Am - F - G 진행의 잔잔한 패드 + 벨 아르페지오 (모노 16bit WAV)."""
    chords = [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63),
              (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)]
    bar = 3.2
    beat = bar / 4
    n = int(seconds * sr)
    frames = bytearray()
    for k in range(n):
        t = k / sr
        c = chords[int(t // bar) % 4]
        tb = t % bar
        env = min(1.0, tb / 0.6) * (1 - 0.25 * (tb / bar))           # 화음마다 부드럽게 시작
        pad = sum(math.sin(2 * math.pi * f * t) + 0.3 * math.sin(4 * math.pi * f * t) for f in c)
        note = c[int(tb // beat) % 3] * 2
        tn = tb % beat
        bell = math.sin(2 * math.pi * note * t) * math.exp(-4.5 * tn)
        fade = min(1.0, t / 0.8, (seconds - t) / 1.2)
        v = (0.045 * pad * env + 0.12 * bell) * max(fade, 0)
        frames += struct.pack("<h", int(max(-1, min(1, v)) * 32000))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def make_reel(data, out_mp4):
    scenes, top3, worst = plan(data)
    tmp = tempfile.mkdtemp()
    pngs = []
    for i, (html, _) in enumerate(scenes):
        p = os.path.join(tmp, f"s{i}.png")
        render_png(html, p, size=(W, H))
        pngs.append(p)
    durs = [d for _, d in scenes]
    total = sum(durs) - FADE * (len(durs) - 1)
    wav = os.path.join(tmp, "bgm.wav")
    _bgm(wav, total)

    parts, chain = [], ""
    for i, d in enumerate(durs):
        fr = int(round(d * FPS))
        parts.append(f"[{i}:v]scale={W*2}:{H*2},zoompan=z='min(zoom+0.0006,1.06)':"
                     f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:s={W}x{H}:fps={FPS},"
                     f"setsar=1,format=yuv420p[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, len(durs)):
        offset += durs[i - 1] - FADE
        label = f"x{i}"
        chain += f";[{prev}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[{label}]"
        prev = label
    fc = ";".join(parts) + chain

    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    for p in pngs:
        cmd += ["-i", p]
    cmd += ["-i", wav, "-filter_complex", fc, "-map", f"[{prev}]", "-map", f"{len(pngs)}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-t", f"{total:.2f}", out_mp4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_mp4):
        raise RuntimeError("릴스 영상 생성 실패: " + (r.stderr or "")[-800:])
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"릴스 생성: {out_mp4} ({total:.1f}초)")
    return top3, worst


def reel_caption(data, top3, worst):
    from datetime import date
    today = date.fromisoformat(data["date"])
    return (f"{today.month}월 {today.day}일 오늘 운 좋은 띠 TOP 3\n"
            f"1위 {top3[0]}띠 · 2위 {top3[1]}띠 · 3위 {top3[2]}띠\n"
            f"오늘은 {worst}띠가 조금 조심하면 좋은 날이에요.\n\n"
            "내 띠는 몇 위였나요? 12띠 전체 운세는 피드 카드에서 확인하세요.\n"
            "같은 띠라도 태어난 달·날·시에 따라 운세는 완전히 달라요. "
            "내 사주로 보는 매일 운세는 프로필 링크에서!\n\n"
            "#오늘의운세 #띠별운세 #운세 #사주 #릴스 #오늘의띠별운세 #운세스타그램 #직장인 #H앤J사주상담소")
