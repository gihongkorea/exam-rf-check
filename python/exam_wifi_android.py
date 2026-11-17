"""
시험장 Wi-Fi / 핫스팟 기준선 감시 (안드로이드 Termux용)

준비 (최초 1회)
  1) F-Droid에서 'Termux'와 'Termux:API' 앱을 둘 다 설치 (둘 다 같은 곳에서 받아야 함)
  2) Termux 실행 후:  pkg update && pkg install python termux-api
  3) 폰 설정 > 앱 > Termux:API > 권한 > '위치' 허용,  폰의 위치(GPS) 켜기
     (안드로이드는 위치 권한이 없으면 와이파이 스캔 결과를 주지 않음)
  4) 이 파일을 Termux 홈으로 복사:  termux-setup-storage 후
     cp ~/storage/downloads/exam_wifi_android.py ~/

사용법
  python exam_wifi_android.py baseline   # 휴대폰 수거 직후 기준선 저장
  python exam_wifi_android.py monitor    # 시험 중 감시 (진동 + 알림)
  python exam_wifi_android.py scan       # 1회 점검
"""
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_FILE = Path.home() / "baseline_wifi.json"
LOG_FILE = Path.home() / f"wifi_log_{datetime.now():%Y%m%d}.csv"

HOTSPOT_KEYWORDS = ["iphone", "galaxy", "androidap", "sm-", "hotspot",
                    "핫스팟", "pixel", "redmi"]
NEAR_DBM = -65          # 이보다 강하면 근거리
RSSI_JUMP_DB = 15       # 기준선 대비 이만큼 세지면 경고
BASELINE_ROUNDS = 3
INTERVAL = 30           # 안드로이드는 스캔 횟수를 제한하므로 30초 이상 권장
ALERT_COOLDOWN = 300


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def scan_wifi():
    raw = run(["termux-wifi-scaninfo"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("스캔 실패: Termux:API 앱 설치/위치 권한을 확인하세요.")
        return []
    if isinstance(data, dict):            # 오류 응답은 dict로 옴
        print("스캔 오류:", data)
        return []
    rows = []
    for ap in data:
        ssid = ap.get("ssid") or "(숨김 SSID)"
        bssid = ap.get("bssid", "?")
        rows.append({
            "key": bssid,
            "label": f"{ssid} ({bssid}, {ap.get('frequency_mhz', '?')}MHz)",
            "rssi": ap.get("rssi", -100),
            "suspect": any(k in ssid.lower() for k in HOTSPOT_KEYWORDS),
        })
    rows.sort(key=lambda r: r["rssi"], reverse=True)
    return rows


def make_baseline():
    devices = {}
    for i in range(BASELINE_ROUNDS):
        print(f"기준선 스캔 {i + 1}/{BASELINE_ROUNDS} ...")
        for r in scan_wifi():
            old = devices.get(r["key"])
            if old is None or r["rssi"] > old["max_rssi"]:
                devices[r["key"]] = {"label": r["label"], "max_rssi": r["rssi"]}
        if i < BASELINE_ROUNDS - 1:
            time.sleep(INTERVAL)
    BASE_FILE.write_text(json.dumps(
        {"created": datetime.now().isoformat(timespec="seconds"),
         "devices": devices}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기준선 저장 완료: {len(devices)}개 → {BASE_FILE}")


def compare(rows, base):
    alerts = []
    for r in rows:
        known = base.get(r["key"])
        if known is None:
            if r["suspect"]:
                alerts.append((r, "★신규 핫스팟 의심"))
            elif r["rssi"] >= NEAR_DBM:
                alerts.append((r, "신규 근거리 AP"))
        elif r["rssi"] - known["max_rssi"] >= RSSI_JUMP_DB and r["rssi"] >= NEAR_DBM:
            alerts.append((r, f"신호 급증 (기준 {known['max_rssi']}dBm)"))
    return alerts


def notify(msg):
    run(["termux-vibrate", "-d", "600"])
    run(["termux-notification", "--title", "시험장 무선 경고", "--content", msg])


def log_alert(r, reason):
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["시각", "기기", "신호(dBm)", "사유"])
        w.writerow([datetime.now().strftime("%H:%M:%S"), r["label"],
                    r["rssi"], reason])


def monitor():
    if not BASE_FILE.exists():
        print("기준선이 없습니다. 먼저 baseline을 실행하세요.")
        return
    base = json.loads(BASE_FILE.read_text(encoding="utf-8"))["devices"]
    print(f"기준선 {len(base)}개 로드. {INTERVAL}초마다 감시 (종료: Ctrl+C)")
    run(["termux-wake-lock"])            # 화면 꺼져도 계속 실행
    last = {}
    while True:
        rows = scan_wifi()
        now = time.time()
        msgs = []
        for r, reason in compare(rows, base):
            if now - last.get(r["key"], 0) < ALERT_COOLDOWN:
                continue
            last[r["key"]] = now
            line = f"{reason} {r['rssi']}dBm {r['label']}"
            print(f"[{datetime.now():%H:%M:%S}] ⚠ {line}")
            log_alert(r, reason)
            msgs.append(line)
        if msgs:
            notify(" / ".join(msgs)[:200])
        else:
            print(f"[{datetime.now():%H:%M:%S}] 이상 없음 (AP {len(rows)}개)")
        time.sleep(INTERVAL)


def scan_once():
    for r in scan_wifi():
        flag = "★핫스팟" if r["suspect"] else ("근거리" if r["rssi"] >= NEAR_DBM else "")
        print(f"  {r['rssi']:>4} dBm  {flag:<6} {r['label']}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    try:
        {"baseline": make_baseline, "monitor": monitor,
         "scan": scan_once}.get(mode, scan_once)()
    except KeyboardInterrupt:
        run(["termux-wake-unlock"])
        print(f"\n종료. 경고 기록: {LOG_FILE}")
