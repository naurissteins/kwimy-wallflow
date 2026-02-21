from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import CONFIG_DIR


@dataclass
class AppConfig:
    wallpaper_dir: str
    matugen_mode: str
    thumbnail_size: int
    batch_size: int
    window_decorations: bool
    show_filenames: bool


DEFAULT_CONFIG = AppConfig(
    wallpaper_dir="~/Pictures/Wallpapers",
    matugen_mode="dark",
    thumbnail_size=256,
    batch_size=16,
    window_decorations=False,
    show_filenames=False,
)


CONFIG_PATH = CONFIG_DIR / "config.json"


def ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_config(DEFAULT_CONFIG)


def load_config() -> AppConfig:
    ensure_config()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CONFIG

    return AppConfig(
        wallpaper_dir=str(data.get("wallpaper_dir", DEFAULT_CONFIG.wallpaper_dir)),
        matugen_mode=str(data.get("matugen_mode", DEFAULT_CONFIG.matugen_mode)),
        thumbnail_size=int(data.get("thumbnail_size", DEFAULT_CONFIG.thumbnail_size)),
        batch_size=int(data.get("batch_size", DEFAULT_CONFIG.batch_size)),
        window_decorations=bool(
            data.get("window_decorations", DEFAULT_CONFIG.window_decorations)
        ),
        show_filenames=bool(data.get("show_filenames", DEFAULT_CONFIG.show_filenames)),
    )


def write_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "wallpaper_dir": config.wallpaper_dir,
        "matugen_mode": config.matugen_mode,
        "thumbnail_size": config.thumbnail_size,
        "batch_size": config.batch_size,
        "window_decorations": config.window_decorations,
        "show_filenames": config.show_filenames,
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
