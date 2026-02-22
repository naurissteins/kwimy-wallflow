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
    thumbnail_shape: str
    batch_size: int
    window_decorations: bool
    show_filenames: bool
    window_width: int
    window_height: int
    scroll_direction: str
    panel_mode: bool
    panel_edge: str
    panel_size: int
    panel_exclusive_zone: int


DEFAULT_CONFIG = AppConfig(
    wallpaper_dir="~/Pictures/Wallpapers",
    matugen_mode="dark",
    thumbnail_size=256,
    thumbnail_shape="landscape",
    batch_size=16,
    window_decorations=False,
    show_filenames=False,
    window_width=900,
    window_height=600,
    scroll_direction="vertical",
    panel_mode=False,
    panel_edge="left",
    panel_size=420,
    panel_exclusive_zone=-1,
)


CONFIG_PATH = CONFIG_DIR / "config.json"


def ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_config(DEFAULT_CONFIG)


def _strip_json_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def load_config() -> AppConfig:
    ensure_config()
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        try:
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(_strip_json_comments(raw))
        except (OSError, json.JSONDecodeError):
            print("Config parse failed; using defaults")
            return DEFAULT_CONFIG

    return AppConfig(
        wallpaper_dir=str(data.get("wallpaper_dir", DEFAULT_CONFIG.wallpaper_dir)),
        matugen_mode=str(data.get("matugen_mode", DEFAULT_CONFIG.matugen_mode)),
        thumbnail_size=int(data.get("thumbnail_size", DEFAULT_CONFIG.thumbnail_size)),
        thumbnail_shape=str(
            data.get("thumbnail_shape", DEFAULT_CONFIG.thumbnail_shape)
        ),
        batch_size=int(data.get("batch_size", DEFAULT_CONFIG.batch_size)),
        window_decorations=bool(
            data.get("window_decorations", DEFAULT_CONFIG.window_decorations)
        ),
        show_filenames=bool(data.get("show_filenames", DEFAULT_CONFIG.show_filenames)),
        window_width=int(data.get("window_width", DEFAULT_CONFIG.window_width)),
        window_height=int(data.get("window_height", DEFAULT_CONFIG.window_height)),
        scroll_direction=str(
            data.get("scroll_direction", DEFAULT_CONFIG.scroll_direction)
        ),
        panel_mode=bool(data.get("panel_mode", DEFAULT_CONFIG.panel_mode)),
        panel_edge=str(data.get("panel_edge", DEFAULT_CONFIG.panel_edge)),
        panel_size=int(data.get("panel_size", DEFAULT_CONFIG.panel_size)),
        panel_exclusive_zone=int(
            data.get("panel_exclusive_zone", DEFAULT_CONFIG.panel_exclusive_zone)
        ),
    )


def write_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "wallpaper_dir": config.wallpaper_dir,
        "matugen_mode": config.matugen_mode,
        "thumbnail_size": config.thumbnail_size,
        "thumbnail_shape": config.thumbnail_shape,
        "batch_size": config.batch_size,
        "window_decorations": config.window_decorations,
        "show_filenames": config.show_filenames,
        "window_width": config.window_width,
        "window_height": config.window_height,
        "scroll_direction": config.scroll_direction,
        "panel_mode": config.panel_mode,
        "panel_edge": config.panel_edge,
        "panel_size": config.panel_size,
        "panel_exclusive_zone": config.panel_exclusive_zone,
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
