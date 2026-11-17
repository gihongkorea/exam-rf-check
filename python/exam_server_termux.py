"""
블루투스 + 와이파이 통합 점검 서버 (안드로이드 Termux용)

웹 브라우저는 보안상 와이파이를 스캔할 수 없습니다.
그래서 이 서버가
  1) 점검 웹 페이지(index.html)를 http://localhost:8000 으로 띄우고
  2) Termux:API로 읽은 와이파이 목록을 /api/wifi 로 페이지에 넘겨줍니다.
→ Chrome 한 화면에서 블루투스(페이지가 직접 스캔)와 와이파이(서버가 전달)를 함께 봅니다.

준비 (최초 1회)
  1) F-Droid에서 'Termux'와 'Termux:API' 설치
  2) Termux에서:  pkg update && pkg install python git termux-api
  3) 폰 설정 > 앱 > Termux:API > 권한 > 위치 허용,  위치(GPS) 켜기
  4) git clone https://github.com/gihongkorea/exam-rf-check

실행
  python exam-rf-check/python/exam_server_termux.py
  → Chrome에서 http://localhost:8000 열기

업데이트
  cd exam-rf-check && git pull

- 이 폰 안(localhost)에서만 열리며, 다른 기기에서는 접속할 수 없습니다.
- 와이파이는 '수신만' 합니다 (주변 AP 목록과 신호세기만 읽음).
"""
import http.server
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

PORT = 8000
POLL_SEC = 10          # 와이파이 목록 갱신 주기 (안드로이드 스캔 제한 때문에 너무 짧게 하지 않음)

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "index.html").exists() else HERE.parent   # index.html이 있는 폴더

state = {"ok": False, "error": "아직 스캔 전", "time": 0, "aps": []}
lock = threading.Lock()


def scan_wifi():
    """termux-wifi-scaninfo 결과를 페이지가 쓰기 쉬운 형태로 바꿈."""
    if not shutil.which("termux-wifi-scaninfo"):
        return False, "termux-api 미설치 (pkg install termux-api)", []
    try:
        res = subprocess.run(["termux-wifi-scaninfo"], capture_output=True,
                             text=True, timeout=20)
        raw = res.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "응답 없음 — Termux:API 앱이 설치돼 있지 않거나 응답하지 않음", []
    if not raw:
        # 출력이 비어 있으면 대부분 Termux:API '앱'이 없거나, Termux와 받은 곳이 다른 경우
        err = res.stderr.strip()[:150]
        return False, ("출력 없음 — Termux:API 앱 설치 여부, Termux와 같은 곳(F-Droid)에서 받았는지 확인"
                       + (f" / 오류: {err}" if err else "")), []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False, "결과 해석 실패 — 받은 내용: " + raw[:150], []
    if isinstance(data, dict):          # 오류는 {"API_ERROR": "..."} 같은 dict로 옴
        return False, "오류: " + json.dumps(data, ensure_ascii=False) + " (위치 권한·GPS 확인)", []
    aps = [{
        "bssid": (ap.get("bssid") or "").lower(),
        "ssid": ap.get("ssid") or "",
        "rssi": ap.get("rssi"),
        "freq": ap.get("frequency_mhz"),
    } for ap in data if ap.get("bssid")]
    return True, "", aps


def poller():
    while True:
        ok, err, aps = scan_wifi()
        with lock:
            state.update(ok=ok, error=err, aps=aps, time=time.time())
        time.sleep(POLL_SEC)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # 항상 최신 페이지 (캐시 문제 방지)
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/api/wifi":
            with lock:
                body = json.dumps(state, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, fmt, *args):   # 요청 로그는 생략 (화면 깔끔하게)
        pass


def main():
    if shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"])        # 화면이 꺼져도 서버 유지
    threading.Thread(target=poller, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"점검 서버 실행 중 → Chrome에서 http://localhost:{PORT} 를 여세요")
    print(f"페이지 폴더: {ROOT}")
    print("종료: Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if shutil.which("termux-wake-unlock"):
            subprocess.run(["termux-wake-unlock"])
        print("서버 종료")


if __name__ == "__main__":
    main()
