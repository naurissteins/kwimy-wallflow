from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .paths import ASSETS_DIR, CONFIG_DIR


LOGGER = logging.getLogger("matuwall.config")
MAX_THUMBNAIL_SIZE = 1000
MAX_BATCH_SIZE = 128
MAX_WINDOW_GRID_COLS = 12
MAX_WINDOW_GRID_ROWS = 12
MIN_PANEL_EXCLUSIVE_ZONE = -1
MAX_PANEL_EXCLUSIVE_ZONE = 4096


@dataclass
class AppConfig:
    wallpaper_dir: str
    matugen_mode: str
    thumbnail_size: int
    thumbnail_shape: str
    batch_size: int
    window_decorations: bool
    window_grid_cols: int
    window_grid_rows: int
    window_grid_max_width_pct: int
    mouse_enabled: bool
    keep_ui_alive: bool
    panel_mode: bool
    panel_edge: str
    panel_thumbs_col: int
    panel_exclusive_zone: int
    panel_margin_top: int
    panel_margin_bottom: int
    panel_margin_left: int
    panel_margin_right: int


DEFAULT_CONFIG = AppConfig(
    wallpaper_dir="~/Pictures/Wallpapers",
    matugen_mode="dark",
    thumbnail_size=256,
    thumbnail_shape="landscape",
    batch_size=16,
    window_decorations=False,
    window_grid_cols=3,
    window_grid_rows=3,
    window_grid_max_width_pct=80,
    mouse_enabled=True,
    keep_ui_alive=False,
    panel_mode=False,
    panel_edge="left",
    panel_thumbs_col=3,
    panel_exclusive_zone=-1,
    panel_margin_top=0,
    panel_margin_bottom=0,
    panel_margin_left=0,
    panel_margin_right=0,
)


CONFIG_PATH = CONFIG_DIR / "config.json"


def ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_config(DEFAULT_CONFIG)
    user_css = CONFIG_DIR / "style.css"
    if not user_css.exists():
        try:
            bundled_css = ASSETS_DIR / "style.css"
            if bundled_css.exists():
                user_css.write_text(
                    bundled_css.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            else:
                user_css.write_text(
                    "# Copy the built-in style here to override app styling.\n",
                    encoding="utf-8",
                )
        except OSError:
            pass


def _strip_json_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


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
            LOGGER.warning("Config parse failed; using defaults")
            return DEFAULT_CONFIG

    return AppConfig(
        wallpaper_dir=str(data.get("wallpaper_dir", DEFAULT_CONFIG.wallpaper_dir)),
        matugen_mode=str(data.get("matugen_mode", DEFAULT_CONFIG.matugen_mode)),
        thumbnail_size=max(
            1,
            min(
                MAX_THUMBNAIL_SIZE,
                int(data.get("thumbnail_size", DEFAULT_CONFIG.thumbnail_size)),
            ),
        ),
        thumbnail_shape=str(
            data.get("thumbnail_shape", DEFAULT_CONFIG.thumbnail_shape)
        ),
        batch_size=_clamp(
            data.get("batch_size", DEFAULT_CONFIG.batch_size),
            1,
            MAX_BATCH_SIZE,
        ),
        window_decorations=bool(
            data.get("window_decorations", DEFAULT_CONFIG.window_decorations)
        ),
        window_grid_cols=_clamp(
            data.get("window_grid_cols", DEFAULT_CONFIG.window_grid_cols),
            1,
            MAX_WINDOW_GRID_COLS,
        ),
        window_grid_rows=_clamp(
            data.get("window_grid_rows", DEFAULT_CONFIG.window_grid_rows),
            1,
            MAX_WINDOW_GRID_ROWS,
        ),
        window_grid_max_width_pct=max(
            20,
            min(
                100,
                int(
                    data.get(
                        "window_grid_max_width_pct",
                        DEFAULT_CONFIG.window_grid_max_width_pct,
                    )
                ),
            ),
        ),
        mouse_enabled=bool(data.get("mouse_enabled", DEFAULT_CONFIG.mouse_enabled)),
        keep_ui_alive=bool(
            data.get("keep_ui_alive", DEFAULT_CONFIG.keep_ui_alive)
        ),
        panel_mode=bool(data.get("panel_mode", DEFAULT_CONFIG.panel_mode)),
        panel_edge=str(data.get("panel_edge", DEFAULT_CONFIG.panel_edge)),
        panel_thumbs_col=max(
            1, int(data.get("panel_thumbs_col", DEFAULT_CONFIG.panel_thumbs_col))
        ),
        panel_exclusive_zone=_clamp(
            data.get("panel_exclusive_zone", DEFAULT_CONFIG.panel_exclusive_zone),
            MIN_PANEL_EXCLUSIVE_ZONE,
            MAX_PANEL_EXCLUSIVE_ZONE,
        ),
        panel_margin_top=int(
            data.get("panel_margin_top", DEFAULT_CONFIG.panel_margin_top)
        ),
        panel_margin_bottom=int(
            data.get("panel_margin_bottom", DEFAULT_CONFIG.panel_margin_bottom)
        ),
        panel_margin_left=int(
            data.get("panel_margin_left", DEFAULT_CONFIG.panel_margin_left)
        ),
        panel_margin_right=int(
            data.get("panel_margin_right", DEFAULT_CONFIG.panel_margin_right)
        ),
    )


def write_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "wallpaper_dir": config.wallpaper_dir,
        "matugen_mode": config.matugen_mode,
        "thumbnail_size": max(
            1, min(MAX_THUMBNAIL_SIZE, int(config.thumbnail_size))
        ),
        "thumbnail_shape": config.thumbnail_shape,
        "batch_size": _clamp(config.batch_size, 1, MAX_BATCH_SIZE),
        "window_decorations": config.window_decorations,
        "window_grid_cols": _clamp(config.window_grid_cols, 1, MAX_WINDOW_GRID_COLS),
        "window_grid_rows": _clamp(config.window_grid_rows, 1, MAX_WINDOW_GRID_ROWS),
        "window_grid_max_width_pct": config.window_grid_max_width_pct,
        "mouse_enabled": config.mouse_enabled,
        "keep_ui_alive": config.keep_ui_alive,
        "panel_mode": config.panel_mode,
        "panel_edge": config.panel_edge,
        "panel_thumbs_col": config.panel_thumbs_col,
        "panel_exclusive_zone": _clamp(
            config.panel_exclusive_zone,
            MIN_PANEL_EXCLUSIVE_ZONE,
            MAX_PANEL_EXCLUSIVE_ZONE,
        ),
        "panel_margin_top": config.panel_margin_top,
        "panel_margin_bottom": config.panel_margin_bottom,
        "panel_margin_left": config.panel_margin_left,
        "panel_margin_right": config.panel_margin_right,
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
