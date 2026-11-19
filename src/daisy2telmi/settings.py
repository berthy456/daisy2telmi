"""Saved options, shared by the command line and the window.

The file is small JSON in the platform's config folder so a GUI can remember a
language and a speech engine between runs; the command line reads it first and
lets flags override it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS: dict = {
    "cut": "chapter",
    "language": "en",
    "announce": "prompt",
    "autoplay": False,
    "lunii": False,
    "tts": "auto",
    "voice": None,
    "command": None,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "daisy2telmi"


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    options = dict(DEFAULTS)
    try:
        stored = json.loads(config_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return options
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", config_path(), exc)
        return options
    if isinstance(stored, dict):
        options.update({key: value for key, value in stored.items() if key in DEFAULTS})
    return options


def save(options: dict) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: options.get(key, DEFAULTS[key]) for key in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
