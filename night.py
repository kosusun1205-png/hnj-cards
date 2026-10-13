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


def write_night(today, angle=""):
    from anthropic import Anthropic
    gz = Solar.fromYmd(today.year, today.month, today.day).getLunar().getDayInGanZhi()
    g, z = GAN[gz[0]], ZHI[gz[1]]
    ko_day = f"{g[0]}{z[0]}일"                 # 예: 경신일 (한글만, 한자 없이)
    prompt = f"""오늘({today.month}월 {today.day}일 {WEEK[today.weekday()]}요일)은 {_ko_pillar(gz)}일입니다.
천간 {gz[0]}({g[0]}, {g[1]}·{g[2]}), 지지 {gz[1]}({z[0]}, {z[1]}, {z[2]}띠).
사주(명리학)에서 오늘 글자가 상징하는 이미지를 바탕으로, 하루를 마친 사람에게 건네는
스레드(Threads) 밤 글을 써 주세요.

가장 중요한 것: 처음 보는 사람이 한 번 읽고 '아, 이런 말이구나' 하고 바로 이해해야 합니다.
수수께끼 같거나, 문장이 뚝뚝 끊기거나, 무슨 뜻인지 생각해야 하는 글은 실패입니다.

글의 흐름 (이 순서대로, 문장끼리 '그래서/그러니까/그런데'로 자연스럽게 이어지게):
1. 주제: 첫 문장은 반드시 '오늘은 {ko_day}이에요.'로 시작하고, 이어서 사주로 보면 어떤 날인지 +
   그게 무슨 뜻인지 한두 문장으로 분명하게.
   (예: '오늘은 {ko_day}이에요. 사주로 보면 큰 바위 같은 날이래요. 쉽게 흔들리지 않는 단단한 기운이 강한 날이라는 뜻이에요.')
2. 공감: 그 기운이 오늘 하루에 어떻게 느껴졌을지, 누구나 겪는 평범한 장면 하나로.
3. 의미: 그래서 오늘의 나에게 어떤 의미인지, 위로나 응원 한두 문장.
4. 마무리: 첫 문장의 이미지로 돌아와 따뜻하게 맺기.

쓰는 법:
- 초등학생도 아는 쉬운 단어. 한자와 명리 용어(오행, 일간, 십신, 경금, 경신일 등) 쓰지 말 것.
- 비유는 처음부터 끝까지 딱 하나. 다른 비유를 덧붙이지 말 것.
- 비유는 누구나 바로 떠올리는 좋은 이미지로 (바위, 보석, 나무, 햇살, 강물처럼).
  칼·불·폭풍처럼 무섭거나 오해할 수 있는 이미지는 피할 것.
- 다정한 존댓말. 공백 포함 250~320자. 3~4문단, 문단 사이 빈 줄 하나.

금지: '나'의 경험담, 지어낸 사례나 일화, '여러분', '~해보는 건 어떨까요', '오늘도 화이팅',
이모지, 해시태그, 질문으로 끝내기, 판매·링크·프로필 언급.
{angle}
글만 출력하세요."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def ask(content):
        resp = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=4096, output_config={"effort": "medium"},
            messages=[{"role": "user", "content": content}],
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"AI가 생성을 거절함: {resp.stop_details}")
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    draft = ask(prompt)
    # 편집자 단계: 사주를 모르는 사람 눈으로 다시 읽고, 이해 안 되거나 끊기는 곳을 고친다
    final = ask(f"""아래는 스레드에 올릴 밤 글 초안입니다. 사주를 전혀 모르는 30대 직장인이 처음 읽는다고 생각하고 검토하세요.
- 무슨 말인지 바로 이해되나요? 비유가 왜 나왔는지 설명돼 있나요?
- 문장끼리 자연스럽게 이어지나요? 갑자기 다른 이야기로 튀는 곳은 없나요?
- 비유가 처음부터 끝까지 딱 하나인가요? (금속·바위·원석처럼 섞이면 하나로 통일)
- 첫 문장 '오늘은 {ko_day}이에요.'는 그대로 둘 것. 그 외의 한자(庚, 辛 등)나 명리 용어는 빼고 쉬운 말로만.
- 마지막 줄이 앞 내용과 연결되나요?
문제가 있으면 고쳐서, 없으면 그대로 최종 글만 출력하세요. 설명이나 머리말 없이 글만.
원래 규칙(쉬운 말, 다정한 존댓말, 공백 포함 250~320자, 이모지·해시태그·질문·판매 문구 금지)은 지키세요.
길면 반복되는 문장과 군더더기를 빼서 줄이세요.

[초안]
{draft}""")
    if len(final) > 400:                       # 그래도 길면 한 번 더 줄이기
        final = ask("아래 글을 뜻과 흐름은 그대로 두고 공백 포함 300자 안팎으로 줄여 주세요. "
                    "글만 출력하세요.\n\n" + final)
    if len(final) > 500:                       # 스레드 한도: 문장 끝에서 자르기
        cut = final[:500]
        final = cut[:max(cut.rfind("요."), cut.rfind("다."), cut.rfind("."))+2].strip()
    if ko_day not in final:                    # 일진 이름이 빠졌으면 첫머리에 붙이기
        final = f"오늘은 {ko_day}이에요. " + final
    return final


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
