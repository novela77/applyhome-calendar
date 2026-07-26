# applyhome-calendar

청약홈(applyhome.co.kr) 청약일정을 매일 긁어 **구독용 iCalendar(.ics)** 로 발행합니다.
애플 캘린더 / 구글 캘린더에서 URL로 구독하면 자동으로 갱신됩니다.

## 구독 주소

```
https://raw.githubusercontent.com/novela77/applyhome-calendar/main/docs/seoul.ics
```

현재 발행 조건: **서울 · 아파트 + 무순위(줍줍) · 2순위 제외, 이번 달부터 4개월치**

- macOS 캘린더 → 파일 → 새로운 캘린더 구독
- iOS 설정 → 앱 → 캘린더 → 계정 → 계정 추가 → 기타 → 구독 캘린더 추가
- 구글 캘린더 → 다른 캘린더 + → URL로 추가

종일 일정으로 등록되고 **하루 전 알림**(`VALARM TRIGGER:-P1D`)이 들어 있습니다.

## 갱신 주기

GitHub Actions가 매일 **05:00 KST**에 실행되며, 일정 내용이 실제로 바뀐 경우에만 커밋합니다.
`.ics`의 `REFRESH-INTERVAL`은 12시간으로 선언돼 있지만, 실제 폴링 간격은 캘린더 앱이 정합니다
(애플은 구독 설정에서 직접 지정 가능).

## 데이터 출처

청약홈 청약캘린더 페이지가 쓰는 공개 JSON 엔드포인트입니다. 인증·쿠키가 필요 없습니다.

```
POST https://www.applyhome.co.kr/ai/aib/selectSubscrptCalender.do
Content-Type: application/json

{"reqData":{"inqirePd":"202607"}}
```

응답 `schdulList[]`의 주요 필드:

| 필드 | 의미 |
|---|---|
| `IN_DATE` | 일정 날짜 (YYYYMMDD) |
| `HOUSE_NM` | 주택명 |
| `SUBSCRPT_AREA_CODE_NM` | 공급지역 (서울, 경기 …) |
| `RCEPT_SE` | 접수구분 코드 |
| `HOUSE_SECD` | 상세공고 라우팅 키 |
| `RESTDE_AT` | `Y`면 일정이 아니라 **공휴일 행** (반드시 제외) |
| `PBLANC_NO` / `HOUSE_MANAGE_NO` | 공고번호 / 주택관리번호 |

`RCEPT_SE` 매핑은 청약캘린더 페이지의 `houseSeClass` 변수와 범례 버튼 텍스트에서 확인했습니다.

| 코드 | 의미 | 코드 | 의미 |
|---|---|---|---|
| 01 | 특별공급 | 05 | 오피스텔/생숙/도생/민간임대 |
| 02 | 1순위 | 06 | 무순위 |
| 03 | 2순위 | 07 | 불법행위재공급 |
| 04 | 공공지원민간임대 | 11 | 임의공급 |

`HOUSE_SECD`는 라벨이 아니라 상세 팝업 URL 분기 키입니다 —
`01·09` → APT 분양정보, `04·06·11` → 무순위/취소후재공급, 나머지 → 오피스텔/민간임대.
이 스크립트는 앞의 둘을 각각 `아파트` / `무순위`로 분류합니다.

## 로컬 실행

```bash
python3 applyhome_calendar.py 202607                                  # CSV, 전국
python3 applyhome_calendar.py --next 4 --region 서울 --apt --remndr   # 서울 아파트+줍줍
python3 applyhome_calendar.py --next 4 --region 서울 --ics > out.ics  # 구독용 ics
python3 applyhome_calendar.py 202607 --json                           # JSON
```

의존성 없음 (표준 라이브러리만 사용).

## 조건 바꾸기

`.github/workflows/build.yml`의 생성 명령에서 `--region` / `--apt` / `--remndr` / `--next` / `--exclude` 를
수정하면 됩니다. 지역을 여러 개 두고 싶으면 파일명을 나눠 여러 줄로 생성하세요.
