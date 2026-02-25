from __future__ import annotations

import argparse
import os
import socket
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .config import AppConfig, load_config
from .paths import (
    APP_ID,
    ASSETS_DIR,
    CACHE_DIR,
    IPC_SOCKET_PATH,
    PID_FILE_PATH,
    UI_PID_FILE_PATH,
    USER_CSS_PATH,
)
from .ui.content import ContentMixin
from .ui.navigation import NavigationMixin
from .ui.panel import LAYER_SHELL_ERROR, LayerShell, PanelMixin
from .ui.runtime import RuntimeMixin
from .ui.thumbnails import ThumbnailMixin


class MatuwallApp(Adw.Application, NavigationMixin, RuntimeMixin, PanelMixin, ContentMixin, ThumbnailMixin):
    LANDSCAPE_RATIO = 9 / 16
    GRID_PADDING = 16
    CARD_PADDING = 8
    CARD_BORDER = 1
    CARD_MARGIN = 16
    SIZE_SAFETY = 0
    HEADER_HEIGHT = 48

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config: AppConfig | None = None
        self._wallpaper_paths: list[Path] = []
        self._load_index = 0
        self._grid_view: Gtk.GridView | None = None
        self._list_store: Gio.ListStore | None = None
        self._scroller: Gtk.ScrolledWindow | None = None
        self._toast_overlay: Adw.ToastOverlay | None = None
        self._window: Adw.ApplicationWindow | None = None
        self._scroll_direction: str = "vertical"
        self._panel_mode = False
        self._panel_edge: str = "left"
        self._panel_size: int = 1
        self._panel_thumbs_col: int = 3
        self._panel_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._backdrop_enabled = True
        self._backdrop_opacity = 0.0
        self._backdrop_click_to_close = True
        self._keep_ui_alive = False
        self._needs_reload = False
        self._daemon_enabled = False
        self._daemon_start_hidden = False
        self._pending_action: str | None = None
        self._quit_requested = False
        self._ipc_socket: socket.socket | None = None
        self._ipc_watch_id: int | None = None
        self._backdrop_window: Gtk.Window | None = None
        self._scrollbar_css_applied = False
        self._snap_anim: Adw.TimedAnimation | None = None
        self._config_css_provider: Gtk.CssProvider | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        if LAYER_SHELL_ERROR:
            self._log(f"gtk4-layer-shell import error: {LAYER_SHELL_ERROR}")
        if os.environ.get("MATUWALL_UI") == "1":
            self._setup_ui_signal_handlers()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        # Keep this override on the concrete Gtk application class so
        # Gio.ApplicationFlags.HANDLES_COMMAND_LINE works correctly.
        return RuntimeMixin.do_command_line(self, command_line)

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        self._ensure_window()

        if self._quit_requested:
            self.quit()
            return

        if self._pending_action == "toggle":
            if self._window and self._window.get_visible():
                self._hide_window()
            else:
                self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "show":
            self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "hide":
            self._hide_window()
            self._pending_action = None
            return

        if self._daemon_start_hidden:
            self._daemon_start_hidden = False
            return

        self._show_window()

    def _show_window(self) -> None:
        if not self._window:
            return
        if self._window.get_visible():
            return
        if self._needs_reload:
            self._reload_content()
        if self._backdrop_enabled:
            self._show_backdrop()
        self._window.present()
        if self._grid_view:
            self._grid_view.grab_focus()
        if self._panel_mode:
            GLib.idle_add(self._refresh_layer_shell)

    def _toggle_window(self) -> None:
        if not self._window:
            return
        if self._window.get_visible():
            self._hide_window()
        else:
            self._show_window()

    def _hide_window(self) -> None:
        if not self._daemon_enabled:
            if self._keep_ui_alive and os.environ.get("MATUWALL_UI") == "1":
                if self._window:
                    self._window.hide()
                if self._backdrop_window:
                    self._backdrop_window.hide()
                return
            self.quit()
            return
        if self._window:
            self._window.hide()
        if self._backdrop_window:
            self._backdrop_window.hide()

    def _ensure_window(self) -> None:
        if self._window:
            return

        self.config = load_config()
        self.CARD_MARGIN = max(0, int(self.config.card_margin))
        self._apply_config_css()
        self._panel_mode = bool(self.config.panel_mode and LayerShell is not None)
        if self._panel_mode and not self._is_wayland():
            self._panel_mode = False
            self._log("Layer-shell requires Wayland; panel_mode disabled")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        window = Adw.ApplicationWindow(application=self)
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
        self._panel_edge = panel_edge
        self._panel_size = panel_size
        self._panel_thumbs_col = panel_thumbs_col
        self._panel_margins = panel_margins
        self._keep_ui_alive = bool(self.config.keep_ui_alive)
        if (
            self._backdrop_enabled
            and self._backdrop_click_to_close
            and self._backdrop_opacity <= 0.0
        ):
            # Keep a tiny alpha so the compositor still delivers input.
            self._backdrop_opacity = 0.01
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
        else:
            target_width, target_height = self._derive_window_size()
            window.set_default_size(target_width, target_height)
            window.set_resizable(False)
        window.set_title("Matuwall")
        if not self._panel_mode:
            window.set_decorated(bool(self.config.window_decorations))
        window.connect("close-request", self._on_close_request)
        self._window = window
        if self.config.panel_mode and LayerShell is None:
            self._log("gtk4-layer-shell not available; panel_mode disabled")
        if self._backdrop_enabled:
            self._ensure_backdrop_window()
        if self._panel_mode:
            self._apply_layer_shell(
                window, panel_edge, panel_size, panel_thumbs_col, panel_margins
            )
        if self._panel_mode:
            self._log(
                "panel_mode=%s edge=%s size=%s thumbs=%s margins=%s backend=%s target=%sx%s"
                % (
                    self._panel_mode,
                    panel_edge,
                    panel_size,
                    panel_thumbs_col,
                    panel_margins,
                    (
                        Gdk.Display.get_default().get_name()
                        if Gdk.Display.get_default()
                        else "none"
                    ),
                    target_width,
                    target_height,
                )
            )
        else:
            self._log(
                "panel_mode=%s edge=%s size=%s backend=%s"
                % (
                    self._panel_mode,
                    panel_edge,
                    panel_size,
                    (
                        Gdk.Display.get_default().get_name()
                        if Gdk.Display.get_default()
                        else "none"
                    ),
                )
            )

        self._build_content()

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

    def _parse_args(self, argv: list[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--daemon", action="store_true")
        parser.add_argument("--toggle", action="store_true")
        parser.add_argument("--show", action="store_true")
        parser.add_argument("--hide", action="store_true")
        parser.add_argument("--quit", action="store_true")
        opts, _ = parser.parse_known_args(argv)
        return opts

    def _load_css(self) -> None:
        css_path = USER_CSS_PATH if USER_CSS_PATH.exists() else ASSETS_DIR / "style.css"
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _apply_config_css(self) -> None:
        if not self.config:
            return
        display = Gdk.Display.get_default()
        if not display:
            return
        margin = max(0, int(self.config.card_margin))
        css = f".matuwall-card {{ margin: {margin}px; }}\n"
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2
        )
        self._config_css_provider = provider

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)

    def do_shutdown(self) -> None:
        self._shutdown_thumbnail_loader()
        if self._daemon_enabled:
            if self._ipc_watch_id is not None:
                try:
                    GLib.source_remove(self._ipc_watch_id)
                except Exception:
                    pass
                self._ipc_watch_id = None
            if self._ipc_socket is not None:
                try:
                    self._ipc_socket.close()
                except Exception:
                    pass
                self._ipc_socket = None
            try:
                if IPC_SOCKET_PATH.exists():
                    IPC_SOCKET_PATH.unlink()
            except OSError:
                pass
            try:
                if PID_FILE_PATH.exists():
                    PID_FILE_PATH.unlink()
            except OSError:
                pass
        if os.environ.get("MATUWALL_UI") == "1":
            try:
                if UI_PID_FILE_PATH.exists():
                    UI_PID_FILE_PATH.unlink()
            except OSError:
                pass
        Adw.Application.do_shutdown(self)


def main() -> int:
    import sys

    app = MatuwallApp()
    return app.run(sys.argv)
