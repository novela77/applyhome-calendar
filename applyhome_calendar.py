#!/usr/bin/env python3
"""청약홈 청약캘린더 일정 수집기.

사용법:
    python3 applyhome_calendar.py 202607                      # 한 달, 전체
    python3 applyhome_calendar.py 202607 202608 202609        # 여러 달
    python3 applyhome_calendar.py 202607 --region 서울 --apt  # 서울 아파트만
    python3 applyhome_calendar.py 202607 --region 서울 --apt --remndr  # + 무순위
    python3 applyhome_calendar.py 202607 --json               # JSON 배열로 출력
    python3 applyhome_calendar.py 202607 202608 --region 서울 --apt --remndr --ics > a.ics

옵션:
    --region <시도>  SUBSCRPT_AREA_CODE_NM 완전일치 (서울, 경기, 부산 ...)
    --apt            아파트 정상공급만
    --remndr         무순위/취소후재공급(줍줍) 계열만
    --ics            iCalendar(.ics) 형식으로 출력 (하루 전 알림 포함)
    --next <N>       오늘이 속한 달부터 N개월치 자동 지정 (KST 기준)
                     --apt 와 함께 쓰면 둘 다 포함. 아무것도 안 주면 전체.
"""
import csv
import datetime
import json
import sys
import urllib.request

URL = "https://www.applyhome.co.kr/ai/aib/selectSubscrptCalender.do"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# 접수구분 코드 — view 페이지의 houseSeClass 매핑 + 범례 버튼 텍스트에서 확인
RCEPT_SE = {
    "01": "특별공급",
    "02": "1순위",
    "03": "2순위",
    "04": "공공지원민간임대",
    "05": "오피스텔/생활숙박시설/도시형생활주택/민간임대",
    "06": "무순위",
    "07": "불법행위재공급",
    "08": "코드08",   # lb_adv_special — 범례에 없음, 실데이터에서도 미관측
    "09": "코드09",   # lb_adv_one
    "10": "코드10",   # lb_adv_two
    "11": "임의공급",
}

# HOUSE_SECD는 라벨이 아니라 상세공고 팝업 라우팅 키 (view 페이지 popUrl 분기)
DETAIL_URL = {
    **{c: "/ai/aia/selectAPTLttotPblancDetail.do" for c in ("01", "09")},
    **{c: "/ai/aia/selectAPTRemndrLttotPblancDetailView.do" for c in ("04", "06", "11")},
}
DETAIL_DEFAULT = "/ai/aia/selectPRMOLttotPblancDetailView.do"

# HOUSE_SECD 그룹 — 상세 팝업 라우팅 분기와 동일하게 나눔
APT_SECD = ("01", "09")            # APT 분양정보 상세 = 아파트 정상공급
REMNDR_SECD = ("04", "06", "11")   # APT 무순위/취소후재공급 상세 = 줍줍 계열


def kind_of(house_secd):
    if house_secd in APT_SECD:
        return "아파트"
    if house_secd in REMNDR_SECD:
        return "무순위"
    return "기타"


def upcoming_months(n):
    """오늘이 속한 달부터 n개월치 YYYYMM 목록 (KST 기준)."""
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch(yyyymm):
    body = json.dumps({"reqData": {"inqirePd": yyyymm}}).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    if data.get("resultCode") != 200:
        raise RuntimeError(f"{yyyymm}: {data.get('msgRtn')}")
    return data["schdulList"]


def normalize(rows):
    out = []
    for r in rows:
        if r.get("RESTDE_AT") == "Y":       # 공휴일 행은 일정이 아님
            continue
        out.append({
            "date": r["IN_DATE"],
            "region": r["SUBSCRPT_AREA_CODE_NM"],
            "name": r["HOUSE_NM"],
            "kind": kind_of(r["HOUSE_SECD"]),
            "type": RCEPT_SE.get(r["RCEPT_SE"], r["RCEPT_SE"]),
            "house_secd": r["HOUSE_SECD"],
            "house_manage_no": r["HOUSE_MANAGE_NO"],
            "pblanc_no": r["PBLANC_NO"],
            "detail_url": DETAIL_URL.get(r["HOUSE_SECD"], DETAIL_DEFAULT),
        })
    out.sort(key=lambda x: (x["date"], x["region"], x["name"]))
    return out


CAL_PAGE = "https://www.applyhome.co.kr/ai/aib/selectSubscrptCalenderView.do"


def esc(s):
    """RFC 5545 텍스트 이스케이프."""
    return (str(s).replace("\\", "\\\\").replace(";", r"\;")
            .replace(",", r"\,").replace("\n", r"\n"))


def fold(line):
    """75옥텟 초과 줄은 접어야 함 (한글은 UTF-8 3바이트라 자주 걸림)."""
    b = line.encode("utf-8")
    if len(b) <= 73:
        return line
    out, cur = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(cur) + len(e) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += e
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def to_ics(rows, alarm_days=1):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0",
         "PRODID:-//applyhome-calendar//KR", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", "X-WR-CALNAME:청약홈 청약일정",
         "X-WR-TIMEZONE:Asia/Seoul", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
         "X-PUBLISHED-TTL:PT12H"]
    for r in rows:
        d = r["date"]
        end = (datetime.datetime.strptime(d, "%Y%m%d")
               + datetime.timedelta(days=1)).strftime("%Y%m%d")
        uid = f'{r["pblanc_no"]}-{d}-{r["type"]}@applyhome'
        L += ["BEGIN:VEVENT",
              f"UID:{esc(uid)}",
              f"DTSTAMP:{stamp}",
              f"DTSTART;VALUE=DATE:{d}",
              f"DTEND;VALUE=DATE:{end}",
              fold("SUMMARY:" + esc(
                  "[{region}] {name} · {type}".format(**r))),
              fold("DESCRIPTION:" + esc(
                  "구분: {kind} / {type}\n공고번호: {pblanc_no}\n"
                  "주택관리번호: {house_manage_no}".format(**r))),
              f"URL:{CAL_PAGE}",
              f'CATEGORIES:{esc(r["kind"])}',
              "TRANSP:TRANSPARENT"]
        if alarm_days:
            L += ["BEGIN:VALARM", "ACTION:DISPLAY",
                  f"TRIGGER:-P{alarm_days}D",
                  fold(f'DESCRIPTION:{esc(r["name"])} {esc(r["type"])} 청약 D-{alarm_days}'),
                  "END:VALARM"]
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def main():
    argv = sys.argv[1:]
    months, region, kinds, as_json = [], None, set(), False
    as_ics = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--ics":
            as_ics = True
        elif a == "--apt":
            kinds.add("아파트")
        elif a == "--remndr":
            kinds.add("무순위")
        elif a == "--region":
            i += 1
            region = argv[i]
        elif a.startswith("--region="):
            region = a.split("=", 1)[1]
        elif a == "--next" or a.startswith("--next="):
            n = int(argv[i + 1]) if a == "--next" else int(a.split("=", 1)[1])
            if a == "--next":
                i += 1
            months += upcoming_months(n)
        else:
            months.append(a)
        i += 1
    if not months:
        sys.exit(__doc__)

    rows = []
    for ym in months:
        rows += normalize(fetch(ym))
    if region:
        rows = [r for r in rows if r["region"] == region]
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]

    if as_ics:
        sys.stdout.write(to_ics(rows))
        return

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]) if rows else [])
    w.writeheader()
    w.writerows(rows)


if __name__ == "__main__":
    main()
