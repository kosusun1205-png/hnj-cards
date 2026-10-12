# -*- coding: utf-8 -*-
"""사주(四柱) 계산 모듈.

lunar_python(순수 파이썬, 절기 기반)으로 사주팔자를 계산하고
결과를 한국어로 읽기 좋게 정리한다. 컴파일 도구가 필요 없다.
"""

import datetime

from lunar_python import Solar, Lunar

# 서울 경도(기본 출생지). 다른 지역이면 birth["longitude"]로 덮어쓸 수 있다.
SEOUL_LON = 126.978

# 한국 일광절약시간제(서머타임) 시행 구간 — 이 기간 출생은 시계가 1시간 빨랐다.
_KOREA_DST = [
    ((1948, 6, 1), (1948, 9, 13)), ((1949, 4, 3), (1949, 9, 11)),
    ((1950, 4, 1), (1950, 9, 10)), ((1951, 5, 6), (1951, 9, 9)),
    ((1955, 5, 5), (1955, 9, 9)), ((1956, 5, 20), (1956, 9, 30)),
    ((1957, 5, 5), (1957, 9, 22)), ((1958, 5, 4), (1958, 9, 21)),
    ((1959, 5, 3), (1959, 9, 20)), ((1960, 5, 1), (1960, 9, 18)),
    ((1987, 5, 10), (1987, 10, 11)), ((1988, 5, 8), (1988, 10, 9)),
]


def _in_dst(dt):
    for (sy, sm, sd), (ey, em, ed) in _KOREA_DST:
        if datetime.datetime(sy, sm, sd) <= dt < datetime.datetime(ey, em, ed):
            return True
    return False


def _standard_meridian(dt):
    # 1954-08-10 ~ 1961-08-09 한국 표준자오선은 동경 127.5도(UTC+8:30)였다.
    if datetime.datetime(1954, 8, 10) <= dt < datetime.datetime(1961, 8, 10):
        return 127.5
    return 135.0


def true_solar_dt(y, mo, d, h, mi, lon=SEOUL_LON):
    """시계시각 -> 사주 계산용 진태양시(경도·서머타임·표준자오선 보정).

    균시차(±16분)는 일반 만세력 관례에 따라 적용하지 않는다.
    """
    dt = datetime.datetime(y, mo, d, h, mi)
    if _in_dst(dt):
        dt -= datetime.timedelta(hours=1)              # 서머타임 해제
    corr = (_standard_meridian(dt) - lon) * 4.0        # 분 (서울 ≈ 32분)
    dt -= datetime.timedelta(minutes=corr)
    return dt

# 천간(天干) 한자 -> 한글 / 오행
GAN = {
    "甲": ("갑", "목", "양"), "乙": ("을", "목", "음"),
    "丙": ("병", "화", "양"), "丁": ("정", "화", "음"),
    "戊": ("무", "토", "양"), "己": ("기", "토", "음"),
    "庚": ("경", "금", "양"), "辛": ("신", "금", "음"),
    "壬": ("임", "수", "양"), "癸": ("계", "수", "음"),
}

# 지지(地支) 한자 -> 한글 / 오행 / 띠
ZHI = {
    "子": ("자", "수", "쥐"), "丑": ("축", "토", "소"),
    "寅": ("인", "목", "호랑이"), "卯": ("묘", "목", "토끼"),
    "辰": ("진", "토", "용"), "巳": ("사", "화", "뱀"),
    "午": ("오", "화", "말"), "未": ("미", "토", "양"),
    "申": ("신", "금", "원숭이"), "酉": ("유", "금", "닭"),
    "戌": ("술", "토", "개"), "亥": ("해", "수", "돼지"),
}

# 십신(十神) 간체 한자 -> 한국어
SHISHEN = {
    "比肩": "비견", "劫财": "겁재", "劫財": "겁재",
    "食神": "식신", "伤官": "상관", "傷官": "상관",
    "偏财": "편재", "偏財": "편재", "正财": "정재", "正財": "정재",
    "七杀": "편관(칠살)", "七殺": "편관(칠살)", "正官": "정관",
    "偏印": "편인", "正印": "정인",
}


# 오행 상생(生)·상극(克)
SHENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
KE = {"목": "토", "화": "금", "토": "수", "금": "목", "수": "화"}


def _ko_pillar(gz):
    """'庚午' -> '경오(庚午)' 형태로 변환."""
    if not gz or len(gz) < 2:
        return gz
    g, z = gz[0], gz[1]
    gk = GAN.get(g, (g,))[0]
    zk = ZHI.get(z, (z,))[0]
    return f"{gk}{zk}({gz})"


def _ko_shishen(s):
    return SHISHEN.get(s, s)


def normalize_year(y):
    """두 자리 연도 보정: 89 -> 1989, 05 -> 2005 (미래는 1900년대로)."""
    try:
        y = int(y)
    except (TypeError, ValueError):
        return y
    if 0 <= y < 100:
        cand = 2000 + y
        # 올해(대략)보다 미래면 1900년대 출생으로 본다
        return cand if cand <= 2026 else 1900 + y
    return y


def ten_god(day_gan, target_gan):
    """일간(day_gan) 기준으로 다른 천간(target_gan)의 십신을 계산."""
    if day_gan not in GAN or target_gan not in GAN:
        return ""
    _, de, dp = GAN[day_gan]   # 일간 오행, 음양
    _, te, tp = GAN[target_gan]
    same = (dp == tp)
    if te == de:
        return "비견" if same else "겁재"
    if SHENG[de] == te:          # 일간이 생함 -> 식상
        return "식신" if same else "상관"
    if KE[de] == te:             # 일간이 극함 -> 재성
        return "편재" if same else "정재"
    if KE[te] == de:             # 상대가 일간을 극함 -> 관성
        return "편관(칠살)" if same else "정관"
    if SHENG[te] == de:          # 상대가 일간을 생함 -> 인성
        return "편인" if same else "정인"
    return ""


# 일진 십신별 그날의 성격 (전문 해석 힌트)
ILJIN_HINT = {
    "비견": "주체성·독립·동료와의 경쟁 또는 협력의 날",
    "겁재": "경쟁·재물 지출 주의·추진력의 날",
    "식신": "표현·여유·먹고 즐김·창의의 날",
    "상관": "재능 발산·말과 행동 주의·변화의 날",
    "편재": "활동적 재물·기회 포착·대인 확장의 날",
    "정재": "성실한 결실·안정적 재물·꼼꼼함의 날",
    "편관(칠살)": "압박·도전·결단·책임이 따르는 날",
    "정관": "질서·신뢰·공적 인정·규칙의 날",
    "편인": "직관·재충전·생각이 깊어지는 날",
    "정인": "도움·배움·문서·안정과 보호의 날",
}


def compute_saju(birth):
    """생년월일시(dict)로 사주를 계산해 dict로 반환.

    birth = {year, month, day, hour, minute, is_lunar, is_leap_month, gender}
    """
    y = normalize_year(birth["year"])
    mo = birth["month"]
    d = birth["day"]
    h = birth.get("hour", 0)
    mi = birth.get("minute", 0)
    lon = birth.get("longitude", SEOUL_LON)

    if birth.get("is_lunar"):
        # 음력 입력 -> 양력 날짜로 변환. 윤달은 월을 음수로 표현.
        month_arg = -mo if birth.get("is_leap_month") else mo
        s = Lunar.fromYmd(y, month_arg, d).getSolar()
        sy, sm, sd = s.getYear(), s.getMonth(), s.getDay()
    else:
        sy, sm, sd = y, mo, d

    # 표시용: 사용자가 입력한 원래 시계시각
    disp_solar = Solar.fromYmdHms(sy, sm, sd, h, mi, 0)
    # 계산용: 진태양시 보정 후의 시각으로 사주를 뽑는다(전문 만세력 방식)
    cdt = true_solar_dt(sy, sm, sd, h, mi, lon)
    calc_solar = Solar.fromYmdHms(cdt.year, cdt.month, cdt.day,
                                  cdt.hour, cdt.minute, 0)

    lunar = calc_solar.getLunar()
    ec = lunar.getEightChar()

    year_gz, month_gz = ec.getYear(), ec.getMonth()
    day_gz, time_gz = ec.getDay(), ec.getTime()

    day_gan = ec.getDayGan()  # 일간 = '나'

    pillars = {
        "년주": _ko_pillar(year_gz),
        "월주": _ko_pillar(month_gz),
        "일주": _ko_pillar(day_gz),
        "시주": _ko_pillar(time_gz),
    }

    ilgan_g, ilgan_o, ilgan_eum = GAN.get(day_gan, (day_gan, "", ""))

    shishen = {
        "년간": _ko_shishen(ec.getYearShiShenGan()),
        "월간": _ko_shishen(ec.getMonthShiShenGan()),
        "시간": _ko_shishen(ec.getTimeShiShenGan()),
    }

    # 오행 분포 (천간 4 + 지지 4 = 8글자)
    dist = {"목": 0, "화": 0, "토": 0, "금": 0, "수": 0}
    for gz in (year_gz, month_gz, day_gz, time_gz):
        if gz[0] in GAN:
            dist[GAN[gz[0]][1]] += 1
        if gz[1] in ZHI:
            dist[ZHI[gz[1]][1]] += 1

    disp_lunar = disp_solar.getLunar()
    return {
        "양력": f"{disp_solar.getYear()}-{disp_solar.getMonth():02d}-"
                f"{disp_solar.getDay():02d} {h:02d}:{mi:02d}",
        "음력": f"{disp_lunar.getYear()}-{disp_lunar.getMonth()}-"
                f"{disp_lunar.getDay()}",
        "띠": ZHI.get(year_gz[1], ("", "", "?"))[2],
        "사주팔자": pillars,
        "일간": f"{ilgan_g}({day_gan}) · {ilgan_o}({ilgan_eum})",
        "일간_한자": day_gan,
        "일간_오행": ilgan_o,
        "십신": shishen,
        "오행분포": dist,
        "성별": birth.get("gender", ""),
    }


def today_iljin(solar_obj):
    """주어진 양력 날짜(Solar)의 일진(그날의 일주)을 한글로 반환."""
    gz = solar_obj.getLunar().getDayInGanZhi()
    return _ko_pillar(gz)


def iljin_relation(saju, solar_obj):
    """오늘 일진이 본인 일간에 미치는 관계(십신)를 계산해 반환."""
    gz = solar_obj.getLunar().getDayInGanZhi()
    day_gan = saju.get("일간_한자", "")
    god = ten_god(day_gan, gz[0]) if gz else ""
    return {
        "일진": _ko_pillar(gz),
        "일진_천간": gz[0] if gz else "",
        "일진오행": GAN.get(gz[0], ("", "", ""))[1] if gz else "",
        "십신": god,
        "해석힌트": ILJIN_HINT.get(god, ""),
    }


def format_saju_text(saju):
    """사주 dict를 프롬프트에 넣기 좋은 한국어 텍스트로."""
    p = saju["사주팔자"]
    s = saju["십신"]
    dist = saju.get("오행분포", {})
    dist_str = ", ".join(f"{k} {v}" for k, v in dist.items())
    return (
        f"- 양력 생일: {saju['양력']} (음력 {saju['음력']}), {saju['띠']}띠, {saju['성별']}\n"
        f"- 사주팔자: 년주 {p['년주']} / 월주 {p['월주']} / "
        f"일주 {p['일주']} / 시주 {p['시주']}\n"
        f"- 일간(본인): {saju['일간']}\n"
        f"- 십신(일간 기준): 년간 {s['년간']}, 월간 {s['월간']}, 시간 {s['시간']}\n"
        f"- 오행 분포(8자): {dist_str}"
    )


def format_iljin_text(rel):
    """오늘 일진 관계를 프롬프트용 텍스트로."""
    return (
        f"- 오늘의 일진: {rel['일진']} (천간 오행 {rel['일진오행']})\n"
        f"- 일간 대비 십신: {rel['십신']} → {rel['해석힌트']}"
    )


if __name__ == "__main__":
    # 빠른 자가 테스트
    demo = {"year": 1990, "month": 5, "day": 15, "hour": 13,
            "minute": 30, "is_lunar": False, "gender": "남"}
    saju = compute_saju(demo)
    print(format_saju_text(saju))
    print("오늘 일진:", today_iljin(Solar.fromYmd(2026, 6, 21)))
