# 시험장 무선 점검 도구 (exam-rf-check)

스마트안경 등 무선기기를 이용한 시험 부정행위에 대비해, 시험장 주변의 **블루투스(BLE)·Wi-Fi 신호를 수신만 해서** 이상 징후를 알려주는 보조 도구입니다.

- 전파를 **보내거나 막지 않습니다** (수동 수신만)
- 통신 **내용은 보지 않습니다** (기기 존재·이름·신호세기만 확인)
- 경고는 감독관 **육안 확인을 위한 참고 신호**이며, 부정행위 판정 근거가 아닙니다

## 구성

| 파일 | 실행 환경 | 감시 대상 |
|---|---|---|
| `index.html` | 브라우저 (Chrome) — GitHub Pages | 블루투스(BLE) |
| `python/exam_rf_scan.py` | PC (Windows 권장) | 블루투스 + Wi-Fi 핫스팟 |
| `python/exam_wifi_android.py` | 안드로이드 Termux | Wi-Fi 핫스팟 |

## 사용 원리: 기준선(baseline) 비교

1. **휴대폰 수거 직후** 기준선 저장 → 그 자리에 원래 있던 기기(학교 AP, 감독관 폰 등)를 기억
2. **시험 중 감시** → 아래 경우에만 경고
   - 기준선에 없던 기기가 안경/핫스팟 계열 이름일 때
   - 기준선에 없던 기기가 근거리(강한 신호)에 나타날 때
   - 기존 기기의 신호가 15dB 이상 급증할 때 (가까이 이동)
   - **스마트안경 제조사 번호**(Meta·Snap·Vuzix·Luxottica)가 보일 때 — 이름이 없어도, 기준선에 있어도 경고
3. 서비스 UUID(Meta·Snap 등록 번호)나 기기 외형(안경)으로도 스마트안경을 의심
4. 감지 목록의 행을 누르면 **상세 정보**: 기기 종류 추정(아이폰/에어팟/Windows PC 등), 대략 거리, 서비스 UUID, 제조사 데이터, 주소 변경 횟수
5. 이름 없는 기기는 주소를 자주 바꾸므로, 1분 안에 같은 제조사·비슷한 신호로 다시 잡히면 경고를 하나로 합쳐 `×N`으로 표시

## 웹 버전 (index.html)

- 주소: https://gihongkorea.github.io/exam-rf-check/
- 안드로이드/PC **Chrome**에서 `chrome://flags` → **Experimental Web Platform features** → Enabled 후 재시작
- 안드로이드: 블루투스·위치(GPS) 켜기, Chrome에 근처 기기·위치 권한 허용
- 감시 중에는 화면을 켠 채 페이지를 띄워 두세요 (화면이 꺼지면 스캔 중지)
- 아이폰 Safari는 웹 블루투스 미지원 → 시연 모드만 가능
- 브라우저는 보안상 Wi-Fi 스캔이 불가능 → 핫스팟은 파이썬 도구 사용

## PC 버전

```bash
pip install bleak
python python/exam_rf_scan.py baseline   # 기준선 저장
python python/exam_rf_scan.py monitor    # 감시 (경고음 + CSV 기록)
python python/exam_rf_scan.py scan       # 1회 점검
```

## 안드로이드 Termux 버전

1. F-Droid에서 `Termux`, `Termux:API` 설치
2. `pkg update && pkg install python termux-api`
3. Termux:API 앱에 위치 권한 허용, GPS 켜기

```bash
python exam_wifi_android.py baseline
python exam_wifi_android.py monitor      # 진동 + 알림
```

## 유의사항

- 실제 시험장 사용 전 소관 교육청 지침을 확인하세요.
- 전파 차단(재밍)은 전파법상 허용되지 않으며, 이 도구는 탐지만 합니다.
