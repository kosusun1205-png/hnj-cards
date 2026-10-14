"""정해진 한국 시각까지 기다리기 (GitHub 예약이 몇 시간씩 밀려도 게시 시각을 일정하게).

사용법: python wait_until.py 6 30      → 한국 06:30 까지 대기 (이미 지났으면 바로 통과)
"""
import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
h, m = int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 0
now = datetime.now(KST)
target = now.replace(hour=h, minute=m, second=0, microsecond=0)
wait = (target - now).total_seconds()
if wait > 0:
    print(f"지금 {now:%H:%M} → {target:%H:%M} 까지 {wait / 60:.0f}분 대기", flush=True)
    time.sleep(wait)
else:
    print(f"지금 {now:%H:%M}, 목표 {target:%H:%M} 지남 → 바로 진행", flush=True)
