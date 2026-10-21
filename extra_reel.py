"""녹음해 둔 영상(오늘의 운세 등)을 정해진 날 인스타 릴스로 게시.

    extra/YYYYMMDD.txt          캡션 (main 브랜치)
    extra-media 브랜치/YYYYMMDD.mp4   영상 (저장소 비대화 방지용 별도 브랜치)
    extra/YYYYMMDD_posted.txt   게시 기록 (있으면 건너뜀)

사용법: python extra_reel.py [YYYYMMDD] [--dry-run]
"""
import os
import sys
import urllib.request
from datetime import datetime

from card import KST, REPO, ig_publish, log


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    day = args[0] if args and args[0] else datetime.now(KST).strftime("%Y%m%d")
    cap, marker = f"extra/{day}.txt", f"extra/{day}_posted.txt"
    if not os.path.exists(cap):
        log(f"{day}: 올릴 녹음 영상 없음")
        return
    if os.path.exists(marker):
        log(f"{day}: 이미 게시됨 (건너뜀)")
        return
    url = f"https://raw.githubusercontent.com/{REPO}/extra-media/{day}.mp4"
    urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)  # 영상이 없으면 여기서 실패
    caption = open(cap, encoding="utf-8").read().strip()
    link = ig_publish(os.environ["IG_TOKEN"], caption, dry_run,
                      media_type="REELS", share_to_feed="true", video_url=url)
    log(f"{day} 녹음 릴스 게시: {link}")
    if not dry_run:
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now(KST).isoformat()} {link}\n")


if __name__ == "__main__":
    main()
