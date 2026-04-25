"""User-home storage so a packaged binary survives across runs.

When sa-rebuild is bundled by PyInstaller, the binary's working directory is
ephemeral. We persist data under ~/.sa-rebuild/ so config/key/state/cache/output
survive across launches and across users on the same machine.

Resolution order (first existing wins):
  1. SA_REBUILD_HOME env var (lets advanced users pin a portable folder)
  2. ./sa-rebuild-data next to the binary (portable mode — power users)
  3. ~/.sa-rebuild (the default for end users)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


_APP_DIRNAME = "sa-rebuild-data"


def _portable_dir() -> Optional[Path]:
    base = Path(sys.argv[0]).resolve().parent if sys.argv else None
    if base is None:
        return None
    candidate = base / _APP_DIRNAME
    return candidate if candidate.exists() else None


def app_home() -> Path:
    env = os.environ.get("SA_REBUILD_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    portable = _portable_dir()
    if portable is not None:
        return portable
    p = Path.home() / ".sa-rebuild"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = app_home() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_dir() -> Path:
    p = app_home() / "state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_dir() -> Path:
    p = app_home() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def input_dir() -> Path:
    p = app_home() / "input"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return app_home() / "settings.json"


def load_settings() -> Dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: Dict[str, Any]) -> None:
    """Atomic write so a crash mid-write doesn't corrupt the file."""
    path = settings_path()
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def get_keepa_api_key() -> Optional[str]:
    """Resolve key from: settings.json → KEEPA_API_KEY env → None."""
    settings = load_settings()
    key = settings.get("keepa_api_key") or os.environ.get("KEEPA_API_KEY")
    return key or None


def set_keepa_api_key(key: str) -> None:
    settings = load_settings()
    settings["keepa_api_key"] = key.strip()
    save_settings(settings)


def bundled_config_yaml() -> Optional[Path]:
    """Locate config.yaml shipped with the binary (PyInstaller _MEIPASS or repo root)."""
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "config.yaml"
        if candidate.exists():
            return candidate
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        c = ancestor / "config.yaml"
        if c.exists():
            return c
    return None
