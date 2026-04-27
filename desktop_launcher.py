"""Desktop launcher — what the bundled binary actually runs.

Boots a local Streamlit server on a free port, then lets Streamlit open the
browser exactly once. Keeps running until the user closes the terminal window /
quits the app from the menu (Ctrl+C).

Single-instance: if an sa-rebuild server is already listening, we just open
the browser to the existing URL instead of starting a second server (which
would cause the "another tab" heartbeat warning).

PyInstaller invokes this as the entry point. When run from source it works
the same way, so you can sanity-check with:
    python desktop_launcher.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import webbrowser
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _app_home() -> Path:
    env = os.environ.get("SA_REBUILD_HOME")
    if env:
        p = Path(env).expanduser().resolve()
    else:
        p = Path.home() / ".sa-rebuild"
    p.mkdir(parents=True, exist_ok=True)
    return p


_LOCK_FILE = _app_home() / "server.lock"


def _read_lock() -> dict | None:
    try:
        return json.loads(_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_lock(port: int) -> None:
    _LOCK_FILE.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")


def _clear_lock() -> None:
    try:
        _LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _server_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _bundled_app_path() -> Path:
    """Locate web/app.py whether running from source or PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "sa_rebuild" / "web" / "app.py"
    return Path(__file__).resolve().parent / "src" / "sa_rebuild" / "web" / "app.py"


def main() -> None:
    # Single-instance check: if a previous server is still listening, just
    # focus that tab instead of spawning a second server.
    lock = _read_lock()
    if lock:
        existing_port = lock.get("port")
        if existing_port and _server_alive(existing_port):
            print(f"sa-rebuild already running on port {existing_port} — opening browser.")
            webbrowser.open(f"http://127.0.0.1:{existing_port}")
            return

    port = _free_port()
    app_path = _bundled_app_path()
    if not app_path.exists():
        print(f"ERROR: app file not found at {app_path}", file=sys.stderr)
        sys.exit(2)

    _write_lock(port)

    # Hand over to Streamlit's CLI runner.
    # headless=false: Streamlit opens the browser exactly once at startup.
    # We do NOT also call webbrowser.open() — that was the source of duplicate tabs.
    from streamlit.web import cli as stcli
    try:
        sys.argv = [
            "streamlit", "run", str(app_path),
            "--server.port", str(port),
            "--server.address", "127.0.0.1",
            "--server.headless", "false",
            "--browser.gatherUsageStats", "false",
            "--global.developmentMode", "false",
            "--server.fileWatcherType", "none",
            "--client.toolbarMode", "viewer",
            "--client.showErrorDetails", "false",
        ]
        sys.exit(stcli.main())
    finally:
        _clear_lock()


if __name__ == "__main__":
    main()
