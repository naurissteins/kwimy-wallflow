from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk

from ..config import load_config
from ..paths import CACHE_DIR
from .panel import LayerShell


class WindowSetupMixin:
    def _ensure_window(self) -> None:
        if self._window:
            return

        self._load_and_apply_config()
        window = Adw.ApplicationWindow(application=self)
        (
            panel_edge,
            panel_size,
            panel_thumbs_col,
            panel_margins,
            monitor_width,
            monitor_height,
        ) = self._resolve_panel_layout()
        self._apply_panel_runtime_state(
            panel_edge, panel_size, panel_thumbs_col, panel_margins
        )
        target_width, target_height = self._configure_window_geometry(
            window,
            panel_edge,
            panel_size,
            panel_thumbs_col,
            panel_margins,
            monitor_width,
            monitor_height,
        )
        self._finalize_window_setup(
            window,
            panel_edge,
            panel_size,
            panel_thumbs_col,
            panel_margins,
            target_width,
            target_height,
        )

    def _load_and_apply_config(self) -> None:
        self.config = load_config()
        self._apply_theme_css()
        self._panel_mode = bool(self.config.panel_mode and LayerShell is not None)
        if self._panel_mode and not self._is_wayland():
            self._panel_mode = False
            self._log("Layer-shell requires Wayland; panel_mode disabled")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _resolve_panel_layout(
        self,
    ) -> tuple[str, int, int, tuple[int, int, int, int], int, int]:
        if not self.config:
            return ("left", 1, 1, (0, 0, 0, 0), 0, 0)

        panel_edge = str(self.config.panel_edge).strip().lower()
        if panel_edge not in {"left", "right", "top", "bottom"}:
            panel_edge = "left"
        if self._panel_mode and panel_edge in {"top", "bottom"}:
            self._scroll_direction = "horizontal"
        else:
            self._scroll_direction = "vertical"

        panel_size = self._derive_panel_size(panel_edge)
        panel_thumbs_col = max(1, int(self.config.panel_thumbs_col))
        panel_margins = (
            max(0, int(self.config.panel_margin_top)),
            max(0, int(self.config.panel_margin_bottom)),
            max(0, int(self.config.panel_margin_left)),
            max(0, int(self.config.panel_margin_right)),
        )
        monitor_width, monitor_height = self._get_primary_monitor_size()
        panel_thumbs_col = self._effective_panel_thumbs_col(
            panel_edge,
            panel_size,
            panel_thumbs_col,
            panel_margins,
            monitor_width,
            monitor_height,
        )
        return (
            panel_edge,
            panel_size,
            panel_thumbs_col,
            panel_margins,
            monitor_width,
            monitor_height,
        )

    def _apply_panel_runtime_state(
        self,
        panel_edge: str,
        panel_size: int,
        panel_thumbs_col: int,
        panel_margins: tuple[int, int, int, int],
    ) -> None:
        self._panel_edge = panel_edge
        self._panel_size = panel_size
        self._panel_thumbs_col = panel_thumbs_col
        self._panel_margins = panel_margins
        self._keep_ui_alive = bool(self.config.keep_ui_alive) if self.config else False
        self._backdrop_opacity = 1.0

    def _configure_window_geometry(
        self,
        window: Adw.ApplicationWindow,
        panel_edge: str,
        panel_size: int,
        panel_thumbs_col: int,
        panel_margins: tuple[int, int, int, int],
        monitor_width: int,
        monitor_height: int,
    ) -> tuple[int, int]:
        if self._panel_mode:
            target_width, target_height = self._panel_target_size(
                panel_edge,
                panel_size,
                panel_thumbs_col,
                monitor_width,
                monitor_height,
                panel_margins,
            )
            window.set_default_size(target_width, target_height)
            window.set_decorated(False)
            window.set_resizable(False)
            return target_width, target_height

        target_width, target_height = self._derive_window_size()
        window.set_default_size(target_width, target_height)
        window.set_resizable(False)
        return target_width, target_height

    def _finalize_window_setup(
        self,
        window: Adw.ApplicationWindow,
        panel_edge: str,
        panel_size: int,
        panel_thumbs_col: int,
        panel_margins: tuple[int, int, int, int],
        target_width: int,
        target_height: int,
    ) -> None:
        window.set_title("Matuwall")
        if not self._panel_mode and self.config:
            window.set_decorated(bool(self.config.window_decorations))
        window.connect("close-request", self._on_close_request)
        self._window = window

        if self.config and self.config.panel_mode and LayerShell is None:
            self._log("gtk4-layer-shell not available; panel_mode disabled")
        if self._panel_mode and self._backdrop_enabled:
            self._ensure_backdrop_window()
        if self._panel_mode:
            self._apply_layer_shell(
                window, panel_edge, panel_size, panel_thumbs_col, panel_margins
            )

        backend = self._display_backend_name()
        if self._panel_mode:
            self._log(
                f"panel_mode={self._panel_mode} edge={panel_edge} size={panel_size} "
                f"thumbs={panel_thumbs_col} margins={panel_margins} backend={backend} "
                f"target={target_width}x{target_height}"
            )
        else:
            self._log(
                f"panel_mode={self._panel_mode} edge={panel_edge} size={panel_size} "
                f"backend={backend}"
            )

        self._build_content()

    @staticmethod
    def _display_backend_name() -> str:
        display = Gdk.Display.get_default()
        if not display:
            return "none"
        return display.get_name() or "none"

    def _derive_window_size(self) -> tuple[int, int]:
        if not self.config:
            return (900, 600)
        cols = max(1, int(self.config.window_grid_cols))
        rows = max(1, int(self.config.window_grid_rows))
        thumb_width = max(1, int(self.config.thumbnail_size))
        shape = (self.config.thumbnail_shape or "landscape").strip().lower()
        if shape == "square":
            thumb_height = thumb_width
        else:
            thumb_height = max(1, int(thumb_width * self.LANDSCAPE_RATIO))

        item_outer_width = (
            thumb_width + (self.CARD_PADDING + self.CARD_BORDER + self.CARD_MARGIN) * 2
        )
        item_outer_height = (
            thumb_height + (self.CARD_PADDING + self.CARD_BORDER + self.CARD_MARGIN) * 2
        )

        width = cols * item_outer_width + self.GRID_PADDING * 2
        height = rows * item_outer_height + self.GRID_PADDING * 2

        width += self.SIZE_SAFETY
        height += self.SIZE_SAFETY
        if self.config.window_decorations:
            height += self.HEADER_HEIGHT

        monitor_width, monitor_height = self._get_primary_monitor_size()
        max_pct = max(20, min(100, int(self.config.window_grid_max_width_pct)))
        if monitor_width > 0:
            width = min(width, int(monitor_width * (max_pct / 100)))
        if monitor_height > 0:
            height = min(height, int(monitor_height * 0.8))

        return max(1, int(width)), max(1, int(height))
