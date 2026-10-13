"""주간 콘텐츠: '같은 띠, 다른 운세' 비교 슬라이드 (매주 일요일).

같은 해에 태어난 같은 띠 가상 인물 두 명(오늘 기운이 좋은 사람 / 도전적인 사람)을
사주로 골라, 오늘 운세를 실제 엔진 근거로 생성해 6장 슬라이드(1080x1350)로 만든다.
광고 문구 없이 '이야기'로 보여주는 것이 목적.
"""
import json
import os
import random

from lunar_python import Solar
from saju import compute_saju, iljin_relation, format_saju_text, format_iljin_text, ZHI

from card import render_png, _esc, log, DEFAULT_MODEL

ORDER = "子丑寅卯辰巳午未申酉戌亥"
GOOD = {"정인", "편인", "정재", "식신", "정관"}
TOUGH = {"편관(칠살)", "상관", "겁재"}
NAMES = {"여": ["민지", "서연", "지은", "수빈", "하은", "유진", "예린", "소윤"],
         "남": ["지훈", "현우", "도윤", "준호", "민재", "성민", "태윤", "건우"]}
WEEK = "월화수목금토일"


def weekly_dir():
    return os.path.join("cards", "weekly")


def weekly_paths(today):
    base = os.path.join(weekly_dir(), f"{today:%Y%m%d}")
    return [f"{base}_{i}.jpg" for i in range(1, 7)], base + "_caption.txt", base + "_threads.txt"


def _hour_ko(h):
    if h < 6:
        return f"새벽 {h}시"
    if h < 12:
        return f"오전 {h}시"
    if h == 12:
        return "낮 12시"
    if h < 18:
        return f"오후 {h - 12}시"
    if h < 21:
        return f"저녁 {h - 12}시"
    return f"밤 {h - 12}시"


def pick_pair(today):
    """같은 해·같은 띠, 오늘 기운이 대비되는 두 사람."""
    rng = random.Random(today.toordinal())
    zi = today.isocalendar()[1] % 12                         # 매주 다른 띠
    year = rng.choice([y for y in range(1980, 2004) if (y - 4) % 12 == zi])
    solar = Solar.fromYmd(today.year, today.month, today.day)
    found = {}
    for _ in range(600):
        b = {"year": year, "month": rng.randint(3, 12), "day": rng.randint(1, 28),
             "hour": rng.randint(0, 23), "minute": 0, "is_lunar": False,
             "is_leap_month": False, "gender": rng.choice(["남", "여"])}
        s = compute_saju(b)
        rel = iljin_relation(s, solar)
        kind = "good" if rel["십신"] in GOOD else "tough" if rel["십신"] in TOUGH else None
        if kind and kind not in found:
            found[kind] = (b, s, rel)
        if len(found) == 2:
            break
    if len(found) < 2:
        raise RuntimeError("대비되는 두 사람을 찾지 못함")
    pair = [found["good"], found["tough"]]
    rng.shuffle(pair)
    used = set()
    people = []
    for b, s, rel in pair:
        name = rng.choice([n for n in NAMES[b["gender"]] if n not in used])
        used.add(name)
        people.append({"name": name, "birth": b, "saju": s, "rel": rel})
    return year, ZHI[ORDER[zi]][2], people


SCHEMA = {
    "type": "object",
    "properties": {
        "people": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"}, "boss": {"type": "string"},
                "quit_pct": {"type": "integer"}, "quit_tip": {"type": "string"},
                "lunch": {"type": "string"}, "oneline": {"type": "string"},
                "boss_short": {"type": "string"}, "lunch_short": {"type": "string"},
            },
            "required": ["headline", "boss", "quit_pct", "quit_tip", "lunch", "oneline",
                         "boss_short", "lunch_short"],
            "additionalProperties": False}},
        "caption": {"type": "string"},
    },
    "required": ["people", "caption"],
    "additionalProperties": False,
}


def write_pair(today, year, tti, people):
    from anthropic import Anthropic
    blocks = "\n\n".join(
        f"[{p['name']}]\n{format_saju_text(p['saju'])}\n{format_iljin_text(p['rel'])}" for p in people)
    prompt = f"""당신은 H&J사주상담소의 인스타그램 작가입니다.
{year}년생 {tti}띠 두 사람의 {today.month}월 {today.day}일 {WEEK[today.weekday()]}요일 운세를 비교하는
슬라이드를 만듭니다. 아래 사주 데이터(특히 '일간 대비 십신')를 근거로, 두 사람의 하루가 확실히
다르게 느껴지도록 쓰세요. 데이터에 없는 내용은 지어내지 마세요.

{blocks}

작성할 것 (JSON, people는 위 순서대로 2명):
- headline: 그 사람의 오늘을 요약하는 한 줄 (22자 이내, 따옴표 없이, 위트 있게)
- boss: 상사·윗사람 운 + 오늘 할 행동 한 문장 (40자 이내)
- quit_pct: 퇴사 충동 게이지 0~100 정수 (도전적인 날일수록 높게)
- quit_tip: 퇴사 충동에 대한 짧은 조언 (22자 이내)
- lunch: 오행에 맞는 점심 메뉴 (18자 이내)
- oneline: 표에 들어갈 오늘 한 줄 (8자 이내, 예: 기대도 되는 날)
- boss_short: 표에 들어갈 상사 운 (8자 이내, 예: 의외로 부드러움)
- lunch_short: 표에 들어갈 점심 (8자 이내)
- caption: 인스타 본문 3~4줄. 두 사람 이야기를 친구에게 들려주듯 쓰고, 띠는 12가지지만 사주는
  518,400가지라는 점을 자연스럽게 언급. 광고·판매·링크 유도 표현 금지, 해시태그 금지.
명리 용어는 쓰지 말고 쉬운 말로. 이모지·특수기호 금지(caption 제외)."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=2048, thinking={"type": "between_tools"},
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default",
                    "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"AI가 생성을 거절함: {resp.stop_details}")
    data = json.loads("".join(b.text for b in resp.content if b.type == "text"))
    if len(data["people"]) != 2:
        raise RuntimeError("인물 2명 문구가 아님")
    return data


CSS = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700;900&display=block" rel="stylesheet">
<style>
:root{--or:#F0641E;--cream:#FBF6EF;--ink:#2B2320;--mute:#8A7A6E;--line:#EADFD3;--blue:#3D5A80;}
html,body{margin:0;padding:0;}
body{width:1080px;height:1350px;overflow:hidden;font-family:'Noto Sans KR',sans-serif;color:var(--ink);position:relative;background:var(--cream);}
.wrap{padding:96px 84px;}
.pg{position:absolute;right:76px;bottom:60px;font-size:26px;font-weight:700;opacity:.45;}
.mark{position:absolute;left:84px;bottom:60px;font-family:'Noto Serif KR',serif;font-weight:900;font-size:24px;letter-spacing:3px;opacity:.55;}
.note{position:absolute;left:0;right:0;bottom:120px;text-align:center;font-size:25px;color:var(--mute);}
em{font-style:normal;color:var(--or);}
.who{display:flex;align-items:center;gap:26px;}
.av{width:130px;height:130px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:56px;font-weight:900;color:#fff;}
.who .n{font-size:58px;font-weight:900;}
.who .b{font-size:30px;color:var(--mute);margin-top:4px;}
.hl{font-size:70px;font-weight:900;line-height:1.3;letter-spacing:-2.5px;margin-top:56px;word-break:keep-all;}
.quote{margin-top:50px;display:flex;flex-direction:column;gap:24px;}
.qq{background:#fff;border-radius:26px;padding:30px 40px;border:2px solid var(--line);}
.qq .k{font-size:30px;font-weight:700;}
.qq .v{font-size:39px;font-weight:500;margin-top:10px;line-height:1.45;word-break:keep-all;}
.t{margin-top:80px;border-radius:28px;overflow:hidden;border:2px solid var(--line);background:#fff;}
.r{display:grid;grid-template-columns:230px 1fr 1fr;border-top:2px solid var(--line);}
.r:first-child{border-top:none;}
.r div{padding:46px 28px;font-size:38px;line-height:1.4;font-weight:500;word-break:keep-all;}
.r .h{font-weight:700;color:var(--mute);background:#F7F2EC;font-size:31px;}
.head div{font-size:42px;font-weight:900;text-align:center;}
</style></head><body>"""
END = "</body></html>"


def _person(p, w, color, year, tti, n):
    b = p["birth"]
    return CSS + f"""
<div class="wrap">
  <div class="who"><div class="av" style="background:{color}">{p['name'][0]}</div>
    <div><div class="n">{p['name']}</div><div class="b">{year}년 {b['month']}월 {b['day']}일 · {_hour_ko(b['hour'])}생 · {tti}띠</div></div></div>
  <div class="hl">"{_esc(w['headline'])}"</div>
  <div class="quote">
    <div class="qq"><div class="k" style="color:{color}">상사 운</div><div class="v">{_esc(w['boss'])}</div></div>
    <div class="qq"><div class="k" style="color:{color}">퇴사 충동 게이지</div><div class="v">{w['quit_pct']}%. {_esc(w['quit_tip'])}</div></div>
    <div class="qq"><div class="k" style="color:{color}">오늘의 점심</div><div class="v">{_esc(w['lunch'])}</div></div>
  </div>
</div>
<div class="note">※ 가상 인물 · H&amp;J 사주딜리버리로 실제 생성한 운세</div>
<div class="mark">H&amp;J</div><div class="pg">{n}/6</div>""" + END


def slides(today, year, tti, people, words):
    a, b = people
    wa, wb = words["people"]
    yy = str(year)[2:]
    s1 = CSS + f"""<style>body{{background:var(--ink);color:#fff;}}</style>
<div class="wrap">
  <div style="font-size:36px;color:#CDBFB4;margin-top:150px;font-weight:500;">{year}년생 {tti}띠 두 사람.<br>{today.year}년 {today.month}월 {today.day}일, {WEEK[today.weekday()]}요일.</div>
  <div style="font-size:104px;font-weight:900;line-height:1.22;letter-spacing:-4px;margin-top:60px;">두 사람의<br>오늘 운세는<br><span style="color:#FF8A4C">같았을까?</span></div>
</div>
<div style="position:absolute;left:84px;bottom:130px;font-size:30px;color:#FF8A4C;font-weight:700;">넘겨서 확인해 보세요 →</div>
<div class="mark" style="color:#fff">H&amp;J</div><div class="pg" style="color:#fff">1/6</div>""" + END
    s4 = CSS + f"""
<div class="wrap">
  <div style="font-size:72px;font-weight:900;letter-spacing:-2.5px;line-height:1.28;">같은 띠, 같은 날.<br>그런데 <em>이렇게나</em> 달랐어요</div>
  <div class="t">
    <div class="r head"><div class="h"></div><div style="color:var(--or)">{a['name']}</div><div style="color:var(--blue)">{b['name']}</div></div>
    <div class="r"><div class="h">오늘 한 줄</div><div>{_esc(wa['oneline'])}</div><div>{_esc(wb['oneline'])}</div></div>
    <div class="r"><div class="h">상사</div><div>{_esc(wa['boss_short'])}</div><div>{_esc(wb['boss_short'])}</div></div>
    <div class="r"><div class="h">퇴사 충동</div><div>{wa['quit_pct']}%</div><div>{wb['quit_pct']}%</div></div>
    <div class="r"><div class="h">점심</div><div>{_esc(wa['lunch_short'])}</div><div>{_esc(wb['lunch_short'])}</div></div>
  </div>
</div>
<div class="note">※ {today.year}년 {today.month}월 {today.day}일, 같은 날 아침 기준</div>
<div class="mark">H&amp;J</div><div class="pg">4/6</div>""" + END
    s5 = CSS + """<style>body{background:var(--or);color:#fff;}</style>
<div class="wrap" style="text-align:center;">
  <div style="font-size:46px;font-weight:700;margin-top:120px;opacity:.9;">띠는</div>
  <div style="font-size:150px;font-weight:900;letter-spacing:-5px;line-height:1.1;">12가지</div>
  <div style="font-size:46px;font-weight:700;margin-top:70px;opacity:.9;">사주는</div>
  <div style="font-size:150px;font-weight:900;letter-spacing:-5px;line-height:1.1;">518,400가지</div>
  <div style="font-size:32px;margin-top:70px;line-height:1.7;color:#FFE3D3;">태어난 해 60 × 달 12 × 날 60 × 시 12<br>띠별 운세가 내 얘기 같지 않았던 이유예요</div>
</div>
<div class="mark" style="color:#fff">H&amp;J</div><div class="pg" style="color:#fff">5/6</div>""" + END
    s6 = CSS + f"""<style>body{{background:var(--ink);color:#fff;}}</style>
<div class="wrap">
  <div style="font-size:96px;font-weight:900;line-height:1.25;letter-spacing:-3.5px;margin-top:220px;">그렇다면<br><span style="color:#FF8A4C">당신의 오늘</span>은<br>어떤 하루일까요?</div>
  <div style="font-size:32px;color:#CDBFB4;margin-top:80px;line-height:1.7;">혹시 {yy}년생 {tti}띠라면, 두 사람 중<br>누구의 하루와 더 닮았나요?</div>
</div>
<div class="mark" style="color:#fff">H&amp;J</div><div class="pg" style="color:#fff">6/6</div>""" + END
    return [s1, _person(a, wa, "var(--or)", year, tti, 2), _person(b, wb, "var(--blue)", year, tti, 3), s4, s5, s6]


def make_weekly(today):
    """슬라이드 6장 jpg + 인스타 캡션 + 스레드 글 생성. 경로 목록 반환."""
    from PIL import Image
    year, tti, people = pick_pair(today)
    words = write_pair(today, year, tti, people)
    jpgs, cap, th = weekly_paths(today)
    os.makedirs(weekly_dir(), exist_ok=True)
    for html, jpg in zip(slides(today, year, tti, people, words), jpgs):
        png = jpg[:-4] + ".png"
        render_png(html, png)
        Image.open(png).convert("RGB").save(jpg, "JPEG", quality=92)
        os.remove(png)
    yy = str(year)[2:]
    story = words["caption"].strip()
    ask = "여러분은 몇 년생 무슨 띠인가요? 두 사람 중 누구와 더 닮았는지 댓글로 알려주세요 🧡"
    tags = f"#{tti}띠 #{yy}년생 #오늘의운세 #사주 #띠별운세 #사주팔자 #운세스타그램 #H앤J사주상담소"
    with open(cap, "w", encoding="utf-8") as f:
        f.write(f"{story}\n\n{ask}\n\n{tags}")
    with open(th, "w", encoding="utf-8") as f:              # 스레드: 자동 답글이 없으니 질문만
        f.write((f"{story}\n\n여러분은 몇 년생 무슨 띠인가요?")[:500])
    log(f"주간 비교 슬라이드 생성: {year}년생 {tti}띠 {people[0]['name']} vs {people[1]['name']}")
    return jpgs, cap, th
