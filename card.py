"""H&J사주상담소 · 인스타그램 '오늘의 띠별 운세' 카드 자동 생성 + 자동 게시.

1) 오늘 일진의 일지(日支)와 12띠의 관계(합·충·원진·오행 생극)를 계산
2) AI가 그 근거로 띠별 한 줄 운세 + 인스타 캡션 작성
3) HTML 카드(1080x1350)를 헤드리스 브라우저로 렌더링 → cards/YYYYMMDD.jpg
4) (워크플로가 커밋·푸시한 뒤) 공개 이미지 주소로 인스타그램 API 게시
5) 결과를 운영자 Gmail로 알림 (실패 시 이미지 첨부 → 수동 업로드)

사용법:
  python card.py generate [--date 2026-10-11]   → cards/에 jpg + 캡션 생성
  python card.py publish <커밋SHA> [미디어SHA] [--dry-run] → 피드·릴스·스레드 게시 + 알림
  python card.py preview [--date ...]            → 생성만 (로컬 확인용)
"""
import os
import sys
import json
import time
import shutil
import smtplib
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from lunar_python import Solar
from saju import GAN, ZHI, SHENG, KE, _ko_pillar

KST = timezone(timedelta(hours=9))
BRAND = "H&J사주상담소"
DEFAULT_MODEL = "claude-sonnet-5-5"
REPO = os.environ.get("GITHUB_REPOSITORY", "kosusun1205-png/hnj-cards")
def load_secrets():
    return {k: os.environ.get(k, "") for k in
            ("ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "IG_TOKEN")}


def log(msg):
    print(f"[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

ORDER = "子丑寅卯辰巳午未申酉戌亥"
YUKHAP = [{"子", "丑"}, {"寅", "亥"}, {"卯", "戌"}, {"辰", "酉"}, {"巳", "申"}, {"午", "未"}]
SAMHAP = ["申子辰", "亥卯未", "寅午戌", "巳酉丑"]
WONJIN = [{"子", "未"}, {"丑", "午"}, {"寅", "酉"}, {"卯", "申"}, {"辰", "亥"}, {"巳", "戌"}]

HASHTAGS = ("#오늘의운세 #띠별운세 #사주 #일진 #운세 #사주딜리버리 "
            "#H앤J사주상담소 #직장인 #출근길 #운세스타그램")


def relation(tti, day):
    """띠 지지(tti)와 오늘 일지(day)의 관계 → (이름, 의미, 별점 1~5)."""
    if tti == day:
        return "같은 기운", "내 기운이 두 배로 강해지는 날", 4
    if abs(ORDER.index(tti) - ORDER.index(day)) == 6:
        return "충", "부딪힘과 변화, 서두르면 손해", 1
    if {tti, day} in YUKHAP:
        return "육합", "손발이 척척 맞고 협력이 잘 되는 날", 5
    if any(tti in g and day in g for g in SAMHAP):
        return "삼합", "같은 편이 생기고 일이 술술 풀리는 날", 5
    if {tti, day} in WONJIN:
        return "원진", "괜히 서운하고 오해가 생기기 쉬운 날", 2
    te, de = ZHI[tti][1], ZHI[day][1]
    if SHENG[de] == te:
        return "생(도움 받음)", "오늘 기운이 나를 밀어주는 날", 4
    if SHENG[te] == de:
        return "설(내가 베풂)", "에너지가 밖으로 나가 지치기 쉬운 날", 3
    if KE[de] == te:
        return "극(눌림)", "압박이 들어오니 몸을 낮추면 이득", 2
    if KE[te] == de:
        return "재(내가 다스림)", "내가 주도권을 쥐고 성과를 챙기는 날", 4
    return "평", "무난하게 흘러가는 날", 3


def build_rows(today):
    gz = Solar.fromYmd(today.year, today.month, today.day).getLunar().getDayInGanZhi()
    day_zhi = gz[1]
    rows = []
    for z in ORDER:
        name, meaning, star = relation(z, day_zhi)
        rows.append({"zhi": z, "tti": ZHI[z][2], "rel": name,
                     "meaning": meaning, "star": star})
    return gz, rows


SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "string"}},
        "caption": {"type": "string"},
    },
    "required": ["headline", "lines", "caption"],
    "additionalProperties": False,
}


def is_soft_day(today):
    """프로필을 부드럽게 언급하는 날(일요일). 나머지 날은 판매 문구 없이 참여 유도만."""
    return today.weekday() == 6


def footer_lines(today):
    """카드·스레드 하단 두 줄 (위: 공감 문장, 아래: 행동 문장)."""
    if is_soft_day(today):
        return ("같은 띠라도 태어난 달·날·시가 다르면 운세도 달라요",
                "내 사주로 보는 매일 운세는 <b>프로필</b>에서")
    return ("같은 띠라도 태어난 달·날·시가 다르면 운세도 달라요",
            "댓글에 내 띠를 남기면 <b>오늘의 한 줄</b>을 답해드려요")


def write_copy(secrets, today, gz, rows):
    from anthropic import Anthropic

    rel_text = "\n".join(
        f"{i+1}. {r['tti']}띠({r['zhi']}) : 오늘 일지와 {r['rel']} → {r['meaning']}"
        for i, r in enumerate(rows))
    gan = GAN[gz[0]]
    ending = ("마지막 줄은 '같은 띠라도 태어난 달·날·시에 따라 하루가 달라져요' 정도로 가볍게."
              if is_soft_day(today) else
              "마지막 줄은 '댓글에 내 띠(예: 쥐띠)나 출생연도를 남겨주시면 오늘의 한 줄을 답글로 드려요' 취지의 참여 질문으로.")
    prompt = f"""당신은 H&J사주상담소의 인스타그램 운세 카드 작가입니다.
오늘({today.month}월 {today.day}일 {"월화수목금토일"[today.weekday()]}요일)의 일진은 {_ko_pillar(gz)}, 천간 오행은 {gan[1]}입니다.
아래는 프로그램이 계산한 12띠와 오늘 일지의 관계입니다. 이 근거를 벗어나 지어내지 마세요.

{rel_text}

작성할 것 (JSON):
- headline: 오늘 하루 전체 분위기를 한 줄로 (15자 이내, 위트 있게)
- lines: 위 순서(쥐띠→돼지띠) 그대로 12개. 각 띠에게 오늘 한 줄 조언.
  ★각 18자 이내★, 친근한 존댓말 또는 명사형 마무리, 직장인 공감 표현 환영.
  명리 용어(충, 합, 원진 등)는 쓰지 말고 쉬운 말로. 이모지·특수기호 금지.
- caption: 인스타 본문 2~3줄. 오늘 분위기를 친구에게 말하듯 요약하고, {ending}
  광고·판매 느낌 금지(가격, 구매, 신청, 링크 클릭 유도 표현 쓰지 말 것).
  해시태그는 넣지 마세요(시스템이 붙임)."""

    client = Anthropic(api_key=secrets["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2048,
        thinking={"type": "between_tools"},
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default",
                    "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"AI가 생성을 거절함: {resp.stop_details}")
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    if len(data["lines"]) != 12:
        raise RuntimeError(f"띠별 문장 개수 오류: {len(data['lines'])}")
    return data


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html(today, gz, rows, copy):
    weekday = "월화수목금토일"[today.weekday()]
    items = []
    for r, line in zip(rows, copy["lines"]):
        stars = "★" * r["star"] + "☆" * (5 - r["star"])
        hot = " hot" if r["star"] >= 5 else (" cold" if r["star"] <= 1 else "")
        items.append(f"""
      <div class="item{hot}">
        <div class="badge"><span class="hz">{r['zhi']}</span><span class="nm">{r['tti']}</span></div>
        <div class="txt"><div class="st">{stars}</div><div class="ln">{_esc(line)}</div></div>
      </div>""")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@700;900&display=block" rel="stylesheet">
<style>
  :root{{--or:#F0641E;--cream:#FBF6EF;--ink:#2B2320;--mute:#8A7A6E;--line:#EADFD3;}}
  html,body{{margin:0;padding:0;}}
  body{{width:1080px;height:1350px;overflow:hidden;background:var(--cream);color:var(--ink);
       font-family:'Noto Sans KR','Malgun Gothic',sans-serif;}}
  .head{{background:var(--or);color:#fff;padding:54px 70px 44px;position:relative;}}
  .brand{{font-family:'Noto Serif KR',serif;font-weight:900;font-size:30px;letter-spacing:4px;}}
  .date{{position:absolute;right:70px;top:56px;font-size:28px;font-weight:500;opacity:.92;}}
  .title{{font-size:76px;font-weight:900;letter-spacing:-2px;margin-top:22px;line-height:1.1;}}
  .sub{{margin-top:16px;font-size:30px;font-weight:500;color:#FFE3D3;}}
  .sub b{{color:#fff;}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px 22px;padding:40px 56px 0;}}
  .item{{display:flex;align-items:center;gap:18px;background:#fff;border:2px solid var(--line);
        border-radius:22px;padding:16px 22px;height:116px;box-sizing:border-box;}}
  .item.hot{{border-color:var(--or);background:#FFF4EC;}}
  .item.cold{{background:#F4F1EE;}}
  .badge{{flex:none;width:76px;height:76px;border-radius:50%;background:var(--ink);color:#fff;
         display:flex;flex-direction:column;align-items:center;justify-content:center;}}
  .hot .badge{{background:var(--or);}}
  .hz{{font-family:'Noto Serif KR',serif;font-size:28px;line-height:1;font-weight:900;}}
  .nm{{font-size:14px;margin-top:3px;font-weight:500;}}
  .txt{{min-width:0;}}
  .st{{color:var(--or);font-size:21px;letter-spacing:2px;line-height:1;}}
  .ln{{font-size:27px;font-weight:700;margin-top:10px;letter-spacing:-.5px;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis;}}
  .foot{{position:absolute;left:0;right:0;bottom:0;background:var(--ink);color:#fff;
        padding:30px 70px;text-align:center;}}
  .foot .q{{font-size:27px;color:#E9DED4;}}
  .foot .a{{font-size:33px;font-weight:900;margin-top:8px;}}
  .foot .a b{{color:#FF9A5C;}}
</style></head><body>
  <div class="head">
    <div class="brand">H&amp;J 사주상담소</div>
    <div class="date">{today.year}. {today.month}. {today.day} ({weekday})</div>
    <div class="title">오늘의 띠별 운세</div>
    <div class="sub">오늘의 일진 <b>{_ko_pillar(gz)}</b> · {_esc(copy['headline'])}</div>
  </div>
  <div class="grid">{''.join(items)}
  </div>
  <div class="foot">
    <div class="q">{footer_lines(today)[0]}</div>
    <div class="a">{footer_lines(today)[1]}</div>
  </div>
</body></html>"""


def _find_browser():
    for p in [os.environ.get("CHROME_PATH", ""),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              shutil.which("google-chrome") or "", shutil.which("chromium") or "",
              shutil.which("chromium-browser") or ""]:
        if p and os.path.exists(p):
            return p
    raise RuntimeError("헤드리스 브라우저(Chrome/Edge)를 찾지 못함")


def render_png(html, out_png, size=(1080, 1350)):
    """HTML → PNG (헤드리스 Chrome/Edge)."""
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "card.html")
    with open(src, "w", encoding="utf-8") as f:
        f.write(html)
    cmd = [_find_browser(), "--headless", "--disable-gpu", "--hide-scrollbars",
           "--no-sandbox", "--virtual-time-budget=10000", f"--window-size={size[0]},{size[1]}",
           f"--screenshot={os.path.abspath(out_png)}", "file:///" + src.replace("\\", "/")]
    subprocess.run(cmd, check=False, capture_output=True, timeout=120)
    if not os.path.exists(out_png):
        raise RuntimeError("카드 이미지 렌더링 실패")


def card_paths(today):
    base = os.path.join("cards", f"{today:%Y%m%d}")
    return base + ".jpg", base + "_caption.txt"


def data_path(today):
    return os.path.join("cards", f"{today:%Y%m%d}.json")


def reel_path(today):
    return os.path.join("cards", f"{today:%Y%m%d}.mp4")      # 저장소엔 안 올림(media 브랜치로)


CHANNELS = ("feed", "reel", "threads")


def posted_marker(today, ch="feed"):
    """채널별 게시 완료 기록 (같은 날 중복 게시 방지)."""
    suffix = "" if ch == "feed" else f"_{ch}"
    return os.path.join("cards", f"{today:%Y%m%d}_posted{suffix}.txt")


def is_weekly_day(today):
    """주간 '같은 띠, 다른 운세' 비교 게시물을 올리는 날(일요일). FORCE_WEEKLY로 테스트 가능."""
    return today.weekday() == 6 or bool(os.environ.get("FORCE_WEEKLY"))


def enabled_channels(today):
    th = bool(os.environ.get("THREADS_TOKEN"))
    chs = [c for c in CHANNELS if c != "threads" or th]
    if is_weekly_day(today):
        chs += ["weekly"] + (["weekly_threads"] if th else [])
    return chs


def generate(today):
    """카드 jpg + 캡션 + 데이터(json) + 릴스 mp4 생성."""
    from PIL import Image
    secrets = load_secrets()
    gz, rows = build_rows(today)
    copy = write_copy(secrets, today, gz, rows)
    caption = copy["caption"].strip() + "\n\n" + HASHTAGS
    os.makedirs("cards", exist_ok=True)
    jpg, cap = card_paths(today)
    png = jpg.replace(".jpg", ".png")
    render_png(render_html(today, gz, rows, copy), png)
    Image.open(png).convert("RGB").save(jpg, "JPEG", quality=92)   # 인스타 API는 JPEG만
    os.remove(png)
    with open(cap, "w", encoding="utf-8") as f:
        f.write(caption)
    data = {"date": today.isoformat(), "gz": gz, "rows": rows, "copy": copy}
    with open(data_path(today), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"카드 생성: {jpg}")
    try:
        import reel
        reel.make_reel(data, reel_path(today))
    except Exception as e:                    # 릴스 실패해도 카드 게시는 진행
        log(f"릴스 생성 실패: {e}")
    if is_weekly_day(today):
        try:
            import compare
            compare.make_weekly(today)
        except Exception as e:
            log(f"주간 비교 슬라이드 생성 실패: {e}")
    return jpg, caption


# ---------- Meta API (인스타그램 / 스레드) ----------

IG_API = "https://graph.instagram.com/v23.0"
TH_API = "https://graph.threads.net/v1.0"


def _api(base, method, path, **params):
    url = f"{base}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            pass
        raise RuntimeError(f"API 오류 {e.code}: {body}") from None


def _wait(base, cid, token, field, ok, tries):
    for _ in range(tries):
        st = _api(base, "GET", cid, fields=field, access_token=token).get(field)
        if st in ok:
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 상태 {st}")
        time.sleep(6)
    raise RuntimeError("컨테이너 준비 시간 초과")


def ig_publish(token, caption, dry_run=False, **media):
    """인스타 게시 (이미지: image_url / 릴스: media_type=REELS, video_url). 게시물 주소 반환."""
    me = _api(IG_API, "GET", "me", fields="user_id,username", access_token=token)
    uid = me["user_id"]
    cid = _api(IG_API, "POST", f"{uid}/media", caption=caption, access_token=token, **media)["id"]
    _wait(IG_API, cid, token, "status_code", ("FINISHED",), 50)     # 영상은 처리에 수십 초~수 분
    if dry_run:
        return "(테스트: 게시 안 함)"
    mid = _api(IG_API, "POST", f"{uid}/media_publish", creation_id=cid, access_token=token)["id"]
    return _api(IG_API, "GET", mid, fields="permalink", access_token=token).get("permalink")


def ig_carousel(token, caption, image_urls, dry_run=False):
    """인스타 여러 장 게시물. 게시물 주소 반환."""
    me = _api(IG_API, "GET", "me", fields="user_id,username", access_token=token)
    uid = me["user_id"]
    kids = [_api(IG_API, "POST", f"{uid}/media", image_url=u, is_carousel_item="true",
                 access_token=token)["id"] for u in image_urls]
    for k in kids:
        _wait(IG_API, k, token, "status_code", ("FINISHED",), 30)
    cid = _api(IG_API, "POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(kids),
               caption=caption, access_token=token)["id"]
    _wait(IG_API, cid, token, "status_code", ("FINISHED",), 30)
    if dry_run:
        return "(테스트: 게시 안 함)"
    mid = _api(IG_API, "POST", f"{uid}/media_publish", creation_id=cid, access_token=token)["id"]
    return _api(IG_API, "GET", mid, fields="permalink", access_token=token).get("permalink")


def th_carousel(token, text, image_urls, dry_run=False):
    """스레드 여러 장 게시물. 게시물 주소 반환."""
    kids = [_api(TH_API, "POST", "me/threads", media_type="IMAGE", image_url=u,
                 is_carousel_item="true", access_token=token)["id"] for u in image_urls]
    for k in kids:
        _wait(TH_API, k, token, "status", ("FINISHED",), 30)
    cid = _api(TH_API, "POST", "me/threads", media_type="CAROUSEL", children=",".join(kids),
               text=text, access_token=token)["id"]
    _wait(TH_API, cid, token, "status", ("FINISHED",), 30)
    if dry_run:
        return "(테스트: 게시 안 함)"
    mid = _api(TH_API, "POST", "me/threads_publish", creation_id=cid, access_token=token)["id"]
    return _api(TH_API, "GET", mid, fields="permalink", access_token=token).get("permalink")


def th_publish(token, text, image_url, dry_run=False):
    """스레드 게시 (이미지 + 글). 게시물 주소 반환."""
    cid = _api(TH_API, "POST", "me/threads", media_type="IMAGE", image_url=image_url,
               text=text, access_token=token)["id"]
    _wait(TH_API, cid, token, "status", ("FINISHED",), 30)
    if dry_run:
        return "(테스트: 게시 안 함)"
    mid = _api(TH_API, "POST", "me/threads_publish", creation_id=cid, access_token=token)["id"]
    return _api(TH_API, "GET", mid, fields="permalink", access_token=token).get("permalink")


def token_check(base, grant, token, name):
    """장기 토큰 연장 시도 → 경고 문구(없으면 None)."""
    try:
        r = _api(base, "GET", "refresh_access_token", grant_type=grant, access_token=token)
    except RuntimeError as e:
        return f"{name} 토큰 연장 실패: {e}"
    days = int(r.get("expires_in", 0)) // 86400
    if r.get("access_token") and r["access_token"] != token:
        return (f"{name} 토큰이 새로 발급돼 GitHub 비밀값 교체가 필요해요 (남은 기간 약 {days}일). "
                f"Claude에게 '{name} 토큰 갱신'이라고 말해 주세요.")
    if days < 15:
        return f"{name} 토큰 만료가 약 {days}일 남았어요. Claude에게 '{name} 토큰 갱신'이라고 말해 주세요."
    return None


def threads_text(data):
    from datetime import date
    today = date.fromisoformat(data["date"])
    head = f"{today.month}월 {today.day}일 ({'월화수목금토일'[today.weekday()]}) 오늘의 띠별 운세\n\n"
    q, a = footer_lines(today)
    if not is_soft_day(today):        # 스레드엔 자동 답글이 없으니 약속 대신 질문만
        a = "여러분의 띠는 오늘 별 몇 개였나요?"
    tail = f"\n\n{q}.\n" + a.replace("<b>", "").replace("</b>", "")
    for fmt in (lambda r, l: f"{r['tti']}띠 {'★' * r['star']}{'☆' * (5 - r['star'])} {l}",
                lambda r, l: f"{r['tti']}띠 {l}"):
        body = "\n".join(fmt(r, l) for r, l in zip(data["rows"], data["copy"]["lines"]))
        if len(head + body + tail) <= 500:            # 스레드 글자 수 제한
            return head + body + tail
    return (head + body)[:500 - len(tail)] + tail


# ---------- 운영자 알림 ----------

def notify_owner(secrets, today, subject, body, jpg=None):
    owner = secrets["GMAIL_ADDRESS"]
    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(BRAND, "utf-8")), owner))
    msg["To"] = owner
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if jpg and os.path.exists(jpg):
        with open(jpg, "rb") as f:
            img = MIMEImage(f.read(), _subtype="jpeg")
        img.add_header("Content-Disposition", "attachment", filename=os.path.basename(jpg))
        msg.attach(img)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(owner, secrets["GMAIL_APP_PASSWORD"])
        s.sendmail(owner, [owner], msg.as_string())


def publish(today, sha, media_sha="", dry_run=False):
    """피드 이미지 · 릴스 · 스레드를 채널별로 게시하고 결과를 운영자에게 메일 1통으로."""
    secrets = load_secrets()
    th_token = os.environ.get("THREADS_TOKEN", "")
    jpg, cap = card_paths(today)
    caption = open(cap, encoding="utf-8").read()
    data = json.load(open(data_path(today), encoding="utf-8"))
    raw = f"https://raw.githubusercontent.com/{REPO}"
    image_url = f"{raw}/{sha}/{jpg.replace(os.sep, '/')}"
    title = f"{today.month}월 {today.day}일 띠별 운세"

    results, failed = [], False
    for ch in enabled_channels(today):
        name = {"feed": "인스타 피드", "reel": "인스타 릴스", "threads": "스레드",
                "weekly": "주간 비교(인스타)", "weekly_threads": "주간 비교(스레드)"}[ch]
        if os.path.exists(posted_marker(today, ch)):
            results.append(f"· {name}: 이미 게시됨 (건너뜀)")
            continue
        try:
            if ch == "feed":
                link = ig_publish(secrets["IG_TOKEN"], caption, dry_run, image_url=image_url)
            elif ch == "reel":
                mp4 = reel_path(today)
                if not (media_sha and os.path.exists(mp4)):
                    raise RuntimeError("릴스 영상이 만들어지지 않았어요")
                import reel
                top3, worst = reel.plan(data)[1:]
                link = ig_publish(secrets["IG_TOKEN"], reel.reel_caption(data, top3, worst), dry_run,
                                  media_type="REELS", share_to_feed="true",
                                  video_url=f"{raw}/{media_sha}/{os.path.basename(mp4)}")
            elif ch in ("weekly", "weekly_threads"):
                import compare
                jpgs, wcap, wth = compare.weekly_paths(today)
                if not all(os.path.exists(p) for p in jpgs):
                    raise RuntimeError("주간 비교 슬라이드가 만들어지지 않았어요")
                urls = [f"{raw}/{sha}/{p.replace(os.sep, '/')}" for p in jpgs]
                if ch == "weekly":
                    link = ig_carousel(secrets["IG_TOKEN"], open(wcap, encoding="utf-8").read(),
                                       urls, dry_run)
                else:
                    link = th_carousel(th_token, open(wth, encoding="utf-8").read(), urls, dry_run)
            else:
                link = th_publish(th_token, threads_text(data), image_url, dry_run)
            if not dry_run:
                with open(posted_marker(today, ch), "w", encoding="utf-8") as f:
                    f.write(f"{datetime.now(KST).isoformat()} {link}\n")
            results.append(f"· {name}: 완료 {link}")
            log(f"{name} 게시: {link}")
        except Exception as e:
            failed = True
            results.append(f"· {name}: ❌ 실패 - {e}")
            log(f"{name} 실패: {e}")

    warns = []
    if today.weekday() == 0 and not dry_run:                 # 월요일마다 토큰 연장
        warns.append(token_check(IG_API, "ig_refresh_token", secrets["IG_TOKEN"], "인스타"))
        if th_token:
            warns.append(token_check(TH_API, "th_refresh_token", th_token, "스레드"))
    warns = [w for w in warns if w]

    tag = "테스트 " if dry_run else ""
    subject = (f"❌ [H&J 자동게시] {title} {tag}일부 실패 - 확인 필요" if failed
               else f"[H&J 자동게시] {title} {tag}완료")
    if warns:
        subject = "⚠️ " + subject
    body = "\n".join(warns + ([""] if warns else []) + ["오늘 게시 결과"] + results)
    if failed:
        body += "\n\n실패한 채널은 첨부 이미지와 아래 캡션으로 직접 올려 주세요."
    body += "\n\n당근 소식에 올릴 날이면 첨부 이미지와 아래 캡션을 쓰세요."
    notify_owner(secrets, today, subject, body + "\n\n──────── 캡션 ────────\n" + caption, jpg)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    today = datetime.now(KST).date()
    if "--date" in args:
        today = datetime.strptime(args[args.index("--date") + 1], "%Y-%m-%d").date()
    cmd = args[0] if args else "preview"
    if cmd == "check":                         # 워크플로: 오늘 모든 채널 게시를 끝냈는지
        done = all(os.path.exists(posted_marker(today, c)) for c in enabled_channels(today))
        log(f"오늘({today}) 게시 기록: {'모두 완료 → 건너뜀' if done else '남은 채널 있음'}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write(f"posted={'true' if done else 'false'}\n")
    elif cmd in ("generate", "preview"):
        jpg, caption = generate(today)
        if cmd == "preview":
            print(caption)
    elif cmd == "publish":
        rest = [a for a in args[1:] if not a.startswith("--") and a != args[args.index("--date") + 1]] \
            if "--date" in args else [a for a in args[1:] if not a.startswith("--")]
        publish(today, rest[0], rest[1] if len(rest) > 1 else "", dry_run="--dry-run" in args)
    else:
        sys.exit(__doc__)
