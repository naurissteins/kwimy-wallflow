from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .paths import CONFIG_DIR

LOGGER = logging.getLogger("matuwall.config")
MAX_THUMBNAIL_SIZE = 1000
MAX_BATCH_SIZE = 128
MAX_WINDOW_GRID_COLS = 12
MAX_WINDOW_GRID_ROWS = 12
MAX_THEME_RADIUS = 64
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
    theme_window_bg: str
    theme_text_color: str
    theme_header_bg_start: str
    theme_header_bg_end: str
    theme_backdrop_bg: str
    theme_card_bg: str
    theme_card_border: str
    theme_card_hover_bg: str
    theme_card_hover_border: str
    theme_card_selected_bg: str
    theme_card_selected_border: str
    theme_window_radius: int
    theme_card_radius: int
    theme_thumb_radius: int
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
    mouse_enabled=False,
    keep_ui_alive=False,
    theme_window_bg="rgba(15, 18, 22, 0.58)",
    theme_text_color="#e7e7e7",
    theme_header_bg_start="rgba(20, 25, 34, 0.58)",
    theme_header_bg_end="rgba(20, 25, 34, 0.78)",
    theme_backdrop_bg="rgba(0, 0, 0, 0.0)",
    theme_card_bg="rgba(255, 255, 255, 0.04)",
    theme_card_border="rgba(255, 255, 255, 0.05)",
    theme_card_hover_bg="rgba(255, 255, 255, 0.08)",
    theme_card_hover_border="rgba(255, 255, 255, 0.2)",
    theme_card_selected_bg="rgba(255, 255, 255, 0.12)",
    theme_card_selected_border="rgba(255, 255, 255, 0.25)",
    theme_window_radius=15,
    theme_card_radius=14,
    theme_thumb_radius=10,
    panel_mode=False,
    panel_edge="left",
    panel_thumbs_col=5,
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


def _strip_json_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] in "}]":
                i += 1
                continue

        out.append(ch)
        i += 1
    return "".join(out)


def _relaxed_json_text(text: str) -> str:
    return _strip_trailing_commas(_strip_json_comments(text))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _pick(
    section: dict[str, object],
    root: dict[str, object],
    key: str,
    default: object,
    legacy_key: str | None = None,
) -> object:
    if key in section:
        return section.get(key)
    if key in root:
        return root.get(key)
    if legacy_key and legacy_key in root:
        return root.get(legacy_key)
    return default


def _sanitize_css_color(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    color = value.strip()
    if not color:
        return default
    if len(color) > 64:
        return default
    if any(ch in color for ch in ("{", "}", ";", "\n", "\r")):
        return default
    return color


def _load_optional_json(path: Path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(_relaxed_json_text(raw))
        except (OSError, json.JSONDecodeError):
            return {}
    return _as_dict(parsed)


def _parse_alpha_component(value: str) -> float | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("%"):
        try:
            return float(raw[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(raw)
    except ValueError:
        return None


def css_color_is_fully_transparent(value: str) -> bool:
    color = value.strip().lower()
    if color == "transparent":
        return True

    if color.startswith("#"):
        hex_value = color[1:]
        if len(hex_value) == 4:
            try:
                return int(hex_value[3] * 2, 16) == 0
            except ValueError:
                return False
        if len(hex_value) == 8:
            try:
                return int(hex_value[6:8], 16) == 0
            except ValueError:
                return False
        return False

    match = re.match(r"^(rgba|hsla)\((.*)\)$", color)
    if not match:
        return False
    content = match.group(2).strip()
    if "/" in content:
        alpha = _parse_alpha_component(content.rsplit("/", 1)[1])
        return alpha is not None and alpha <= 0.0
    parts = [part.strip() for part in content.split(",")]
    if len(parts) < 4:
        return False
    alpha = _parse_alpha_component(parts[-1])
    return alpha is not None and alpha <= 0.0


def load_config() -> AppConfig:
    ensure_config()
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        try:
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(_relaxed_json_text(raw))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Config parse failed; using defaults")
            return DEFAULT_CONFIG

    root = _as_dict(data)
    main = _as_dict(root.get("main"))
    theme = _as_dict(root.get("theme"))
    panel = _as_dict(root.get("panel"))
    colors_path_candidates = [CONFIG_PATH.parent / "colors.json"]
    if CONFIG_DIR != CONFIG_PATH.parent:
        colors_path_candidates.append(CONFIG_DIR / "colors.json")
    colors_root: dict[str, object] = {}
    for candidate in colors_path_candidates:
        loaded = _load_optional_json(candidate)
        if loaded:
            colors_root = loaded
            break
    colors_theme = _as_dict(colors_root.get("theme"))

    def _pick_theme_color(key: str, default: str, legacy_key: str) -> object:
        base_value = _pick(theme, root, key, default, legacy_key=legacy_key)
        if key in colors_theme:
            return colors_theme.get(key)
        if legacy_key in colors_theme:
            return colors_theme.get(legacy_key)
        if key in colors_root:
            return colors_root.get(key)
        if legacy_key in colors_root:
            return colors_root.get(legacy_key)
        return base_value

    return AppConfig(
        wallpaper_dir=str(_pick(main, root, "wallpaper_dir", DEFAULT_CONFIG.wallpaper_dir)),
        matugen_mode=str(_pick(main, root, "matugen_mode", DEFAULT_CONFIG.matugen_mode)),
        thumbnail_size=max(
            1,
            min(
                MAX_THUMBNAIL_SIZE,
                int(_pick(main, root, "thumbnail_size", DEFAULT_CONFIG.thumbnail_size)),
            ),
        ),
        thumbnail_shape=str(_pick(main, root, "thumbnail_shape", DEFAULT_CONFIG.thumbnail_shape)),
        batch_size=_clamp(
            _pick(main, root, "batch_size", DEFAULT_CONFIG.batch_size),
            1,
            MAX_BATCH_SIZE,
        ),
        window_decorations=bool(
            _pick(
                main,
                root,
                "window_decorations",
                DEFAULT_CONFIG.window_decorations,
            )
        ),
        window_grid_cols=_clamp(
            _pick(main, root, "window_grid_cols", DEFAULT_CONFIG.window_grid_cols),
            1,
            MAX_WINDOW_GRID_COLS,
        ),
        window_grid_rows=_clamp(
            _pick(main, root, "window_grid_rows", DEFAULT_CONFIG.window_grid_rows),
            1,
            MAX_WINDOW_GRID_ROWS,
        ),
        window_grid_max_width_pct=max(
            20,
            min(
                100,
                int(
                    _pick(
                        main,
                        root,
                        "window_grid_max_width_pct",
                        DEFAULT_CONFIG.window_grid_max_width_pct,
                    )
                ),
            ),
        ),
        mouse_enabled=bool(_pick(main, root, "mouse_enabled", DEFAULT_CONFIG.mouse_enabled)),
        keep_ui_alive=bool(_pick(main, root, "keep_ui_alive", DEFAULT_CONFIG.keep_ui_alive)),
        theme_window_bg=_sanitize_css_color(
            _pick_theme_color(
                "window_bg",
                DEFAULT_CONFIG.theme_window_bg,
                "theme_window_bg",
            ),
            DEFAULT_CONFIG.theme_window_bg,
        ),
        theme_text_color=_sanitize_css_color(
            _pick_theme_color(
                "text_color",
                DEFAULT_CONFIG.theme_text_color,
                "theme_text_color",
            ),
            DEFAULT_CONFIG.theme_text_color,
        ),
        theme_header_bg_start=_sanitize_css_color(
            _pick_theme_color(
                "header_bg_start",
                DEFAULT_CONFIG.theme_header_bg_start,
                "theme_header_bg_start",
            ),
            DEFAULT_CONFIG.theme_header_bg_start,
        ),
        theme_header_bg_end=_sanitize_css_color(
            _pick_theme_color(
                "header_bg_end",
                DEFAULT_CONFIG.theme_header_bg_end,
                "theme_header_bg_end",
            ),
            DEFAULT_CONFIG.theme_header_bg_end,
        ),
        theme_backdrop_bg=_sanitize_css_color(
            _pick_theme_color(
                "backdrop_bg",
                DEFAULT_CONFIG.theme_backdrop_bg,
                "theme_backdrop_bg",
            ),
            DEFAULT_CONFIG.theme_backdrop_bg,
        ),
        theme_card_bg=_sanitize_css_color(
            _pick_theme_color(
                "card_bg",
                DEFAULT_CONFIG.theme_card_bg,
                "theme_card_bg",
            ),
            DEFAULT_CONFIG.theme_card_bg,
        ),
        theme_card_border=_sanitize_css_color(
            _pick_theme_color(
                "card_border",
                DEFAULT_CONFIG.theme_card_border,
                "theme_card_border",
            ),
            DEFAULT_CONFIG.theme_card_border,
        ),
        theme_card_hover_bg=_sanitize_css_color(
            _pick_theme_color(
                "card_hover_bg",
                DEFAULT_CONFIG.theme_card_hover_bg,
                "theme_card_hover_bg",
            ),
            DEFAULT_CONFIG.theme_card_hover_bg,
        ),
        theme_card_hover_border=_sanitize_css_color(
            _pick_theme_color(
                "card_hover_border",
                DEFAULT_CONFIG.theme_card_hover_border,
                "theme_card_hover_border",
            ),
            DEFAULT_CONFIG.theme_card_hover_border,
        ),
        theme_card_selected_bg=_sanitize_css_color(
            _pick_theme_color(
                "card_selected_bg",
                DEFAULT_CONFIG.theme_card_selected_bg,
                "theme_card_selected_bg",
            ),
            DEFAULT_CONFIG.theme_card_selected_bg,
        ),
        theme_card_selected_border=_sanitize_css_color(
            _pick_theme_color(
                "card_selected_border",
                DEFAULT_CONFIG.theme_card_selected_border,
                "theme_card_selected_border",
            ),
            DEFAULT_CONFIG.theme_card_selected_border,
        ),
        theme_window_radius=_clamp(
            _pick(
                theme,
                root,
                "window_radius",
                DEFAULT_CONFIG.theme_window_radius,
                legacy_key="theme_window_radius",
            ),
            0,
            MAX_THEME_RADIUS,
        ),
        theme_card_radius=_clamp(
            _pick(
                theme,
                root,
                "card_radius",
                DEFAULT_CONFIG.theme_card_radius,
                legacy_key="theme_card_radius",
            ),
            0,
            MAX_THEME_RADIUS,
        ),
        theme_thumb_radius=_clamp(
            _pick(
                theme,
                root,
                "thumb_radius",
                DEFAULT_CONFIG.theme_thumb_radius,
                legacy_key="theme_thumb_radius",
            ),
            0,
            MAX_THEME_RADIUS,
        ),
        panel_mode=bool(_pick(panel, root, "panel_mode", DEFAULT_CONFIG.panel_mode)),
        panel_edge=str(_pick(panel, root, "panel_edge", DEFAULT_CONFIG.panel_edge)),
        panel_thumbs_col=max(
            1,
            int(_pick(panel, root, "panel_thumbs_col", DEFAULT_CONFIG.panel_thumbs_col)),
        ),
        panel_exclusive_zone=_clamp(
            _pick(
                panel,
                root,
                "panel_exclusive_zone",
                DEFAULT_CONFIG.panel_exclusive_zone,
            ),
            MIN_PANEL_EXCLUSIVE_ZONE,
            MAX_PANEL_EXCLUSIVE_ZONE,
        ),
        panel_margin_top=int(
            _pick(panel, root, "panel_margin_top", DEFAULT_CONFIG.panel_margin_top)
        ),
        panel_margin_bottom=int(
            _pick(
                panel,
                root,
                "panel_margin_bottom",
                DEFAULT_CONFIG.panel_margin_bottom,
            )
        ),
        panel_margin_left=int(
            _pick(panel, root, "panel_margin_left", DEFAULT_CONFIG.panel_margin_left)
        ),
        panel_margin_right=int(
            _pick(panel, root, "panel_margin_right", DEFAULT_CONFIG.panel_margin_right)
        ),
    )


def write_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "main": {
            "wallpaper_dir": config.wallpaper_dir,
            "matugen_mode": config.matugen_mode,
            "thumbnail_size": max(1, min(MAX_THUMBNAIL_SIZE, int(config.thumbnail_size))),
            "thumbnail_shape": config.thumbnail_shape,
            "batch_size": _clamp(config.batch_size, 1, MAX_BATCH_SIZE),
            "window_decorations": config.window_decorations,
            "window_grid_cols": _clamp(config.window_grid_cols, 1, MAX_WINDOW_GRID_COLS),
            "window_grid_rows": _clamp(config.window_grid_rows, 1, MAX_WINDOW_GRID_ROWS),
            "window_grid_max_width_pct": config.window_grid_max_width_pct,
            "mouse_enabled": config.mouse_enabled,
            "keep_ui_alive": config.keep_ui_alive,
        },
        "theme": {
            "window_bg": _sanitize_css_color(
                config.theme_window_bg, DEFAULT_CONFIG.theme_window_bg
            ),
            "text_color": _sanitize_css_color(
                config.theme_text_color, DEFAULT_CONFIG.theme_text_color
            ),
            "header_bg_start": _sanitize_css_color(
                config.theme_header_bg_start, DEFAULT_CONFIG.theme_header_bg_start
            ),
            "header_bg_end": _sanitize_css_color(
                config.theme_header_bg_end, DEFAULT_CONFIG.theme_header_bg_end
            ),
            "backdrop_bg": _sanitize_css_color(
                config.theme_backdrop_bg, DEFAULT_CONFIG.theme_backdrop_bg
            ),
            "card_bg": _sanitize_css_color(config.theme_card_bg, DEFAULT_CONFIG.theme_card_bg),
            "card_border": _sanitize_css_color(
                config.theme_card_border, DEFAULT_CONFIG.theme_card_border
            ),
            "card_hover_bg": _sanitize_css_color(
                config.theme_card_hover_bg, DEFAULT_CONFIG.theme_card_hover_bg
            ),
            "card_hover_border": _sanitize_css_color(
                config.theme_card_hover_border, DEFAULT_CONFIG.theme_card_hover_border
            ),
            "card_selected_bg": _sanitize_css_color(
                config.theme_card_selected_bg, DEFAULT_CONFIG.theme_card_selected_bg
            ),
            "card_selected_border": _sanitize_css_color(
                config.theme_card_selected_border,
                DEFAULT_CONFIG.theme_card_selected_border,
            ),
            "window_radius": _clamp(config.theme_window_radius, 0, MAX_THEME_RADIUS),
            "card_radius": _clamp(config.theme_card_radius, 0, MAX_THEME_RADIUS),
            "thumb_radius": _clamp(config.theme_thumb_radius, 0, MAX_THEME_RADIUS),
        },
        "panel": {
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
        },
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
