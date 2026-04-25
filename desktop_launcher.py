"""Desktop launcher — what the bundled binary actually runs.

Boots a local Streamlit server on a free port, then opens the user's default
browser to it. Keeps running until the user closes the terminal window /
quits the app from the menu (Ctrl+C).

PyInstaller invokes this as the entry point. When run from source it works
the same way, so you can sanity-check with:
    python desktop_launcher.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _bundled_app_path() -> Path:
    """Locate web/app.py whether running from source or PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "sa_rebuild" / "web" / "app.py"
    return Path(__file__).resolve().parent / "src" / "sa_rebuild" / "web" / "app.py"


def main() -> None:
    port = _free_port()
    app_path = _bundled_app_path()
    if not app_path.exists():
        print(f"ERROR: app file not found at {app_path}", file=sys.stderr)
        sys.exit(2)

    # Streamlit settings tuned for a single-user local desktop experience.
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")          # don't print browser opening msg twice
    os.environ.setdefault("STREAMLIT_SERVER_PORT", str(port))
    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

    # Open the browser once Streamlit is listening.
    def _open_when_ready() -> None:
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):  # wait up to 30s
            time.sleep(0.5)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                continue
        webbrowser.open(url)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    # Hand over to Streamlit's CLI runner.
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", str(app_path),
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
        "--server.fileWatcherType", "none",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
