"""
시험장 무선기기 점검 스캐너 v2 (PC용: BLE + Wi-Fi)  ─ 기준선(baseline) 비교 기능

- 수동(passive) 수신만 합니다: 전파를 '듣기'만 하고, 보내거나 막지 않습니다.
- 통신 '내용'은 보지 않고, 기기 존재 / 이름 / 신호세기(RSSI)만 확인합니다.

설치:  pip install bleak

사용법
  1) 기준선 저장 (휴대폰 수거·전원 OFF 확인 직후, 1교시 시작 전):
       python exam_rf_scan.py baseline
  2) 시험 중 감시 (30초마다 스캔, 기준선에 없던 '가까운' 신호 → 경고음 + 기록):
       python exam_rf_scan.py monitor
  3) 한 번만 점검:
       python exam_rf_scan.py scan
"""
import asyncio
import csv
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from bleak import BleakScanner

# ───────────── 설정값 (현장에 맞게 조정) ─────────────
BASE_FILE = Path("baseline.json")
LOG_FILE = Path(f"scan_log_{datetime.now():%Y%m%d}.csv")

GLASSES_KEYWORDS = ["ray-ban", "rayban", "meta", "oakley", "glass",
                    "xreal", "rokid", "even g", "inmo", "solos"]
HOTSPOT_KEYWORDS = ["iphone", "galaxy", "androidap", "sm-", "hotspot",
                    "핫스팟", "pixel", "redmi"]

NEAR_DBM = {"BLE": -60, "WIFI": -65}  # 이보다 강하면 '근거리'(대략 수 m 이내)
RSSI_JUMP_DB = 15        # 기준선 기기의 신호가 이만큼 세지면 '신호 급증' 경고
BASELINE_ROUNDS = 3      # 기준선 만들 때 반복 스캔 횟수
MONITOR_INTERVAL = 30    # 감시 주기(초)
BLE_SCAN_SEC = 8         # 1회 BLE 수신 시간(초)
ALERT_COOLDOWN = 300     # 같은 기기 재경고 최소 간격(초)


# ───────────── 1. 스캔 ─────────────
def ble_key(name, addr, maker_ids):
    """기기 식별키. 폰은 BLE 주소를 수시로 바꾸므로(주소 랜덤화)
    이름이 있으면 '이름+제조사ID'로, 없으면 주소로 식별."""
    if name:
        return f"BLE|{name}|{','.join(sorted(maker_ids))}"
    return f"BLE|{addr}"


async def scan_ble(seconds=BLE_SCAN_SEC):
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name or ""
        maker_ids = [hex(k) for k in adv.manufacturer_data.keys()]
        rows.append({
            "kind": "BLE",
            "key": ble_key(name, addr, maker_ids),
            "label": name or f"(이름 없음) {addr}",
            "rssi": adv.rssi,
            "suspect": any(k in name.lower() for k in GLASSES_KEYWORDS),
        })
    return rows


def parse_netsh(text):
    """netsh 출력에서 SSID / BSSID / 신호%를 뽑아냄 (한글·영문 Windows 모두)."""
    rows, ssid, bssid = [], None, None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^SSID \d+\s*:\s*(.*)$", line)
        if m:
            ssid = m.group(1) or "(숨김 SSID)"
            continue
        m = re.match(r"^BSSID \d+\s*:\s*([0-9a-fA-F:]{17})", line)
        if m:
            bssid = m.group(1).lower()
            continue
        m = re.match(r"^(신호|Signal)\s*:\s*(\d+)%", line)
        if m and ssid and bssid:
            pct = int(m.group(2))
            rows.append({
                "kind": "WIFI",
                "key": f"WIFI|{bssid}",
                "label": f"{ssid} ({bssid})",
                "rssi": pct // 2 - 100,          # % → dBm 근사 변환
                "suspect": any(k in ssid.lower() for k in HOTSPOT_KEYWORDS),
            })
    return rows


def scan_wifi():
    if platform.system() != "Windows":
        return []
    out = subprocess.run(
        ["netsh", "wlan", "show", "networks", "mode=bssid"],
        capture_output=True, text=True, encoding="cp949", errors="ignore",
    ).stdout
    return parse_netsh(out)


async def scan_all():
    rows = await scan_ble()
    rows += scan_wifi()
    rows.sort(key=lambda r: r["rssi"], reverse=True)   # 가까운 순
    return rows


def is_near(r):
    return r["rssi"] >= NEAR_DBM[r["kind"]]


# ───────────── 2. 기준선 저장 ─────────────
async def make_baseline():
    devices = {}
    for i in range(BASELINE_ROUNDS):
        print(f"기준선 스캔 {i + 1}/{BASELINE_ROUNDS} ...")
        for r in await scan_all():
            old = devices.get(r["key"])
            # 여러 번 스캔 중 가장 강했던 신호를 기준으로 기억
            if old is None or r["rssi"] > old["max_rssi"]:
                devices[r["key"]] = {"kind": r["kind"], "label": r["label"],
                                     "max_rssi": r["rssi"]}
    data = {"created": datetime.now().isoformat(timespec="seconds"),
            "devices": devices}
    BASE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"\n기준선 저장 완료: {len(devices)}개 기기 → {BASE_FILE.resolve()}")


# ───────────── 3. 비교 (핵심 로직) ─────────────
def compare(rows, base):
    """기준선과 비교해 경고 목록을 돌려줌."""
    alerts = []
    for r in rows:
        known = base.get(r["key"])
        if known is None:
            if r["suspect"]:
                alerts.append((r, "★신규 의심기기(안경/핫스팟 이름)"))
            elif is_near(r):
                alerts.append((r, "신규 근거리 신호"))
        elif r["rssi"] - known["max_rssi"] >= RSSI_JUMP_DB and is_near(r):
            alerts.append((r, f"신호 급증 (기준 {known['max_rssi']}dBm)"))
    return alerts


def beep():
    if platform.system() == "Windows":
        import winsound
        winsound.Beep(1500, 400)
    else:
        print("\a", end="")


def log_alert(r, reason):
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["시각", "종류", "기기", "신호(dBm)", "사유", "식별키"])
        w.writerow([datetime.now().strftime("%H:%M:%S"), r["kind"],
                    r["label"], r["rssi"], reason, r["key"]])


# ───────────── 4. 감시 루프 ─────────────
async def monitor():
    if not BASE_FILE.exists():
        print("baseline.json이 없습니다. 먼저 'baseline'을 실행하세요.")
        return
    base = json.loads(BASE_FILE.read_text(encoding="utf-8"))["devices"]
    print(f"기준선 {len(base)}개 기기 로드. {MONITOR_INTERVAL}초마다 감시합니다. "
          f"(종료: Ctrl+C)\n")
    last_alert = {}   # key → 마지막 경고 시각 (같은 기기 반복 경고 방지)

    while True:
        rows = await scan_all()
        now = time.time()
        fired = 0
        for r, reason in compare(rows, base):
            if now - last_alert.get(r["key"], 0) < ALERT_COOLDOWN:
                continue
            last_alert[r["key"]] = now
            fired += 1
            print(f"[{datetime.now():%H:%M:%S}] ⚠ {reason:<28} "
                  f"{r['rssi']:>4}dBm  {r['kind']:<4} {r['label']}")
            log_alert(r, reason)
        if fired:
            beep()
        else:
            print(f"[{datetime.now():%H:%M:%S}] 이상 없음 (감지 {len(rows)}개)")
        await asyncio.sleep(MONITOR_INTERVAL)


# ───────────── 5. 1회 점검 ─────────────
async def scan_once():
    for r in await scan_all():
        flag = "★의심" if r["suspect"] else ("근거리" if is_near(r) else "")
        print(f"  {r['rssi']:>4} dBm  {flag:<5} {r['kind']:<4} {r['label']}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    try:
        asyncio.run({"baseline": make_baseline, "monitor": monitor,
                     "scan": scan_once}.get(mode, scan_once)())
    except KeyboardInterrupt:
        print(f"\n종료. 경고 기록: {LOG_FILE.resolve()}")
