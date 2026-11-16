"""녹음해 둔 영상(오늘의 운세 등)을 정해진 날 인스타 릴스로 게시.

    extra/YYYYMMDD.txt          캡션 (main 브랜치)
    extra-media 브랜치/YYYYMMDD.mp4   영상 (저장소 비대화 방지용 별도 브랜치)
    extra/YYYYMMDD_posted.txt   게시 기록 (있으면 건너뜀)

유튜브 쇼츠는 같은 방식으로 shorts/ 칸에 둠 (--slot shorts, 저녁 9시 게시):
    shorts/YYYYMMDD.txt, extra-media 브랜치/shorts/YYYYMMDD.mp4, shorts/YYYYMMDD_posted.txt

사용법: python extra_reel.py [YYYYMMDD] [--dry-run] [--slot shorts]
"""
import os
import sys
import urllib.request
from datetime import datetime

from card import KST, REPO, ig_publish, log


def main():
    argv = sys.argv[1:]
    slot = argv[argv.index("--slot") + 1] if "--slot" in argv else "extra"
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--slot")]
    dry_run = "--dry-run" in argv
    day = args[0] if args and args[0] else datetime.now(KST).strftime("%Y%m%d")
    cap, marker = f"{slot}/{day}.txt", f"{slot}/{day}_posted.txt"
    if not os.path.exists(cap):
        log(f"{day}: 올릴 {slot} 영상 없음")
        return
    if os.path.exists(marker):
        log(f"{day}: 이미 게시됨 (건너뜀)")
        return
    media = f"{day}.mp4" if slot == "extra" else f"{slot}/{day}.mp4"
    url = f"https://raw.githubusercontent.com/{REPO}/extra-media/{media}"
    urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)  # 영상이 없으면 여기서 실패
    caption = open(cap, encoding="utf-8").read().strip()
    link = ig_publish(os.environ["IG_TOKEN"], caption, dry_run,
                      media_type="REELS", share_to_feed="true", video_url=url,
                      **({"is_ai_generated": "true"} if os.path.exists(f"{slot}/{day}_ai.txt") else {}))
    log(f"{day} {slot} 릴스 게시: {link}")
    if not dry_run:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now(KST).isoformat()} {link}\n")


if __name__ == "__main__":
    main()
