from __future__ import annotations

import os
from pathlib import Path

APP_ID = "com.kwimy.Wallflow"
APP_NAME = "kwimy-wallflow"


def _xdg_dir(env_key: str, fallback: Path) -> Path:
    value = os.environ.get(env_key)
    if value:
        return Path(value)
    return fallback


HOME = Path.home()
CONFIG_DIR = _xdg_dir("XDG_CONFIG_HOME", HOME / ".config") / APP_NAME
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", HOME / ".cache") / APP_NAME
RUNTIME_DIR = _xdg_dir(
    "XDG_RUNTIME_DIR", Path("/run/user") / str(os.getuid())
) / APP_NAME

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
IPC_SOCKET_PATH = RUNTIME_DIR / "ipc.sock"
PID_FILE_PATH = RUNTIME_DIR / "daemon.pid"
