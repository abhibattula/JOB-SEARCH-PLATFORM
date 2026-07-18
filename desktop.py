"""Run this one file and the Job Engine opens as a desktop app.

The web server starts inside this process on 127.0.0.1 and a native window
(Edge WebView2 on Windows, WKWebView on macOS) opens onto it. Closing the
window shuts everything down. If no webview backend is available, the app
falls back to opening your default browser and keeps serving until Ctrl+C.
"""
from dotenv import load_dotenv

load_dotenv()

import socket
import threading
import time
import webbrowser

import httpx
import uvicorn

from app import maybe_start_scheduler
from engine import db

WINDOW_TITLE = "Job Engine"


def pick_port() -> int:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 8000))
            return 8000
        except OSError:
            pass
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_ready(url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> None:
    db.init_db()
    maybe_start_scheduler()
    port = pick_port()
    url = f"http://127.0.0.1:{port}"

    server = uvicorn.Server(
        uvicorn.Config("web.main:app", host="127.0.0.1", port=port, log_level="warning")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    if not wait_until_ready(url):
        raise SystemExit("Server failed to start — check the console for errors.")

    try:
        import webview  # pywebview

        webview.create_window(WINDOW_TITLE, url, width=1280, height=880)
        webview.start()  # blocks until the window is closed
    except Exception as exc:
        print(f"Native window unavailable ({type(exc).__name__}: {exc}).")
        print(f"Opening your browser at {url} instead — press Ctrl+C here to quit.")
        webbrowser.open(url)
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    server.should_exit = True
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
