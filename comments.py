"""인스타 댓글 자동 답글: 댓글에 띠(쥐띠…)나 출생연도(96년생…)가 있으면 그 띠의 오늘 운세로 답글.

- 최근 게시물의 최근 3일 댓글만 확인, 이미 답한 댓글·내 댓글은 건너뜀
- 띠를 알 수 없는 댓글엔 답하지 않음 (스팸처럼 보이지 않게)
- 운세는 그날 생성된 cards/YYYYMMDD.json 을 사용

사용법: python comments.py [--dry-run]
"""
import glob
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta

from card import _api, IG_API, KST, log

TTI = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
ALIAS = {"범": "호랑이", "잔나비": "원숭이"}
MAX_REPLIES = 20

TEMPLATES = [
    "@{u}님 {t}띠 오늘은 {s}! \"{l}\" 좋은 하루 보내세요 🧡",
    "@{u}님 반가워요! {t}띠 오늘의 한 줄은 \"{l}\" ({s}) 이에요 🍀",
    "@{u}님 {t}띠는 오늘 {s}, \"{l}\" 기억해 두세요 ✨",
]
SOFT_CTA = " 태어난 달·날·시까지 보면 훨씬 정확하게 볼 수 있어요. 궁금하시면 프로필 링크 참고해 주세요!"


def detect_tti(text):
    m = re.search(r"(쥐|소|호랑이|범|토끼|용|뱀|말|양|원숭이|잔나비|닭|개|돼지)\s*띠", text)
    if m:
        return ALIAS.get(m.group(1), m.group(1))
    m = re.search(r"(?<!\d)((?:19|20)\d{2}|\d{2})\s*년\s*생", text) or \
        re.search(r"(?<!\d)((?:19|20)\d{2})\s*년", text)
    if m:
        y = int(m.group(1))
        if y < 100:
            y += 1900 if y > 30 else 2000
        if 1920 <= y <= datetime.now(KST).year:
            return TTI[(y - 4) % 12]                 # 양력 연도 기준 (입춘 전 출생은 예외 있음)
    return None


def latest_data():
    today = f"{datetime.now(KST):%Y%m%d}"
    files = [f for f in sorted(glob.glob(os.path.join("cards", "[0-9]" * 8 + ".json")))
             if os.path.basename(f)[:8] <= today]
    if not files:
        raise RuntimeError("운세 데이터(cards/*.json)가 없어요")
    return json.load(open(files[-1], encoding="utf-8"))


def reply_text(user, tti, data):
    i = TTI.index(tti)
    row, line = data["rows"][i], data["copy"]["lines"][i]
    stars = "★" * row["star"] + "☆" * (5 - row["star"])
    msg = random.choice(TEMPLATES).format(u=user, t=tti, s=stars, l=line)
    if random.random() < 0.3:
        msg += SOFT_CTA
    return msg


def run(dry_run=False):
    token = os.environ["IG_TOKEN"]
    me = _api(IG_API, "GET", "me", fields="user_id,username", access_token=token)
    data = latest_data()
    since = datetime.now(KST) - timedelta(days=3)
    media = _api(IG_API, "GET", f"{me['user_id']}/media", fields="id,timestamp",
                 limit=10, access_token=token).get("data", [])
    done = checked = 0
    for m in media:
        comments = _api(IG_API, "GET", f"{m['id']}/comments",
                        fields="id,text,username,timestamp,replies{username}",
                        limit=50, access_token=token).get("data", [])
        for c in comments:
            if done >= MAX_REPLIES:
                break
            user = c.get("username", "")
            if not user or user == me["username"]:
                continue
            ts = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if ts < since:
                continue
            replies = (c.get("replies") or {}).get("data", [])
            if any(r.get("username") == me["username"] for r in replies):
                continue
            checked += 1
            tti = detect_tti(c.get("text", ""))
            if not tti:
                continue
            msg = reply_text(user, tti, data)
            if dry_run:
                log(f"[테스트] @{user} '{c.get('text', '')[:30]}' → {msg}")
            else:
                _api(IG_API, "POST", f"{c['id']}/replies", message=msg, access_token=token)
                log(f"답글: @{user} ({tti}띠)")
            done += 1
    log(f"댓글 확인 {checked}개, 답글 {done}개 (기준 데이터 {data['date']})")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
