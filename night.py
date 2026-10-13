"""스레드 밤 글: 그날 일진의 상징 하나로 쓰는 짧고 쉬운 위로의 글 (글만, 이미지 없음).

- 아침 자동 게시 때 미리 만들어 cards/YYYYMMDD_night.txt 로 저장 (알림 메일로 미리보기)
- 밤 워크플로가 그 글을 스레드에 게시, 게시 기록 cards/YYYYMMDD_posted_night.txt

사용법: python night.py generate|publish [--date 2026-10-14] [--dry-run]
"""
import json
import os
import sys
from datetime import datetime

from lunar_python import Solar
from saju import GAN, ZHI, _ko_pillar

from card import _api, _wait, TH_API, KST, DEFAULT_MODEL, log

WEEK = "월화수목금토일"


def night_path(today):
    return os.path.join("cards", f"{today:%Y%m%d}_night.txt")


def night_marker(today):
    return os.path.join("cards", f"{today:%Y%m%d}_posted_night.txt")


def write_night(today):
    from anthropic import Anthropic
    gz = Solar.fromYmd(today.year, today.month, today.day).getLunar().getDayInGanZhi()
    g, z = GAN[gz[0]], ZHI[gz[1]]
    prompt = f"""오늘({today.month}월 {today.day}일 {WEEK[today.weekday()]}요일)은 {_ko_pillar(gz)}일입니다.
천간 {gz[0]}({g[0]}, {g[1]}·{g[2]}), 지지 {gz[1]}({z[0]}, {z[1]}, {z[2]}띠).
명리학에서 이 글자가 상징하는 자연 이미지를 하나 골라, 하루를 마친 사람에게 건네는
스레드(Threads) 밤 글을 써 주세요.

누구나 한 번 읽고 바로 이해되게:
- 초등학생도 아는 쉬운 단어만. 한자어·어려운 말·명리 용어 금지(오행, 일간, 십신 같은 말 X).
- 한 문장은 20자 안팎으로 짧게. 전체 5~7줄.
- 비유는 딱 하나만. 첫 줄에 '오늘은 ○○의 날이래요'처럼 아주 쉽게 소개하고 그 비유 하나로 끝까지.
- 다정한 존댓말. 읽는 사람의 하루를 말해 줄 것 (출근길, 회의, 퇴근길처럼 누구나 아는 장면 하나).

금지:
- '나'의 경험담, 지어낸 상담 사례나 일화
- '~해보는 건 어떨까요', '여러분', '오늘도 화이팅', 과한 위로, 같은 문장 구조 반복
- 이모지, 해시태그, 질문으로 끝내기, 판매·링크·프로필 언급
- 마지막에 교훈 요약. 마지막 줄은 짧은 여운으로.

글만 출력하세요."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=1024, thinking={"type": "between_tools"},
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"AI가 생성을 거절함: {resp.stop_details}")
    return "".join(b.text for b in resp.content if b.type == "text").strip()[:500]


def make_night(today):
    """밤 글 생성 (이미 있으면 그대로 둠 → 미리보기한 글이 그대로 게시됨)."""
    p = night_path(today)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    text = write_night(today)
    os.makedirs("cards", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"밤 글 생성: {p}")
    return text


def publish_night(today, dry_run=False):
    if os.path.exists(night_marker(today)):
        log("오늘 밤 글은 이미 게시됨")
        return
    token = os.environ["THREADS_TOKEN"]
    text = make_night(today)
    cid = _api(TH_API, "POST", "me/threads", media_type="TEXT", text=text, access_token=token)["id"]
    _wait(TH_API, cid, token, "status", ("FINISHED",), 20)
    if dry_run:
        log("[테스트] 밤 글 게시 직전까지 확인 (게시 안 함)")
        return
    mid = _api(TH_API, "POST", "me/threads_publish", creation_id=cid, access_token=token)["id"]
    link = _api(TH_API, "GET", mid, fields="permalink", access_token=token).get("permalink")
    with open(night_marker(today), "w", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST).isoformat()} {link}\n")
    log(f"밤 글 게시: {link}")


if __name__ == "__main__":
    args = sys.argv[1:]
    today = datetime.now(KST).date()
    if "--date" in args:
        today = datetime.strptime(args[args.index("--date") + 1], "%Y-%m-%d").date()
    cmd = args[0] if args else "generate"
    if cmd == "generate":
        print(make_night(today))
    elif cmd == "publish":
        publish_night(today, dry_run="--dry-run" in args)
    else:
        sys.exit(__doc__)
