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


def _acquire_app_mutex() -> None:
    """Named mutex the Inno installer's AppMutex directive checks, so an
    upgrade reliably detects (and closes) a running instance instead of
    hitting in-use files mid-copy (008 FR-031). Held for process lifetime —
    deliberately never closed."""
    import sys

    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "JobEngineRunning")


def _install_crash_hooks() -> None:
    """008 (FR-033): unhandled exceptions — main thread AND background
    threads (refresh pipeline, scheduler, Apply Assist) — land in app.log
    with a crash marker the UI surfaces once on next launch."""
    import sys
    import threading
    import traceback

    from engine import paths

    def _record(exc_type, exc, tb) -> None:
        try:
            data_dir = paths.data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(data_dir / "app.log", "a", encoding="utf-8", errors="replace") as f:
                f.write("\n--- UNHANDLED EXCEPTION ---\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
            (data_dir / "crash.marker").write_text(
                f"{exc_type.__name__}: {exc}"[:300], encoding="utf-8"
            )
        except Exception:
            pass

    previous_hook = sys.excepthook

    def _sys_hook(exc_type, exc, tb):
        _record(exc_type, exc, tb)
        previous_hook(exc_type, exc, tb)

    sys.excepthook = _sys_hook

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        _record(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _thread_hook


def _redirect_streams_when_windowed() -> None:
    """Windowed (console-less) builds have sys.stdout/stderr = None, which
    breaks uvicorn's logging setup. Point them at a log file in the data dir —
    which doubles as the place users can look when something goes wrong."""
    import sys

    if sys.stdout is not None and sys.stderr is not None:
        return
    from engine import paths

    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / "app.log", "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def main() -> None:
    _redirect_streams_when_windowed()
    _acquire_app_mutex()
    _install_crash_hooks()
    db.init_db()
    maybe_start_scheduler()
    port = pick_port()
    url = f"http://127.0.0.1:{port}"

    # Written for tooling (packaging/smoke_test.py) to discover the port
    # without parsing netstat/lsof output, which is fragile and platform-
    # specific — this file is the single source of truth for "what port did
    # this instance actually bind."
    from engine import paths

    port_file = paths.data_dir()
    port_file.mkdir(parents=True, exist_ok=True)
    (port_file / "port.txt").write_text(str(port), encoding="utf-8")

    # Import the app object directly (a "module:attr" string breaks under PyInstaller)
    from web.main import app as web_app

    server = uvicorn.Server(
        uvicorn.Config(web_app, host="127.0.0.1", port=port, log_level="warning")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    if not wait_until_ready(url):
        raise SystemExit(
            "Server failed to start — see the log at "
            f"{paths.data_dir() / 'app.log'} for the reason."
        )

    try:
        import webview  # pywebview

        # 008 (FR-001/FR-004/FR-005): the shell must behave like a browser —
        # selectable text, working downloads, external links opening in the
        # system browser. pywebview's defaults disable all three.
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=1280,
            height=880,
            min_size=(960, 640),
            text_select=True,
            confirm_close=True,
        )
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
