from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from .config import AppConfig
from .paths import APP_ID, IPC_SOCKET_PATH, PID_FILE_PATH, UI_PID_FILE_PATH
from .ui.bootstrap import AppBootstrapMixin
from .ui.content import ContentMixin
from .ui.navigation import NavigationMixin
from .ui.panel import LAYER_SHELL_ERROR, PanelMixin
from .ui.runtime import RuntimeMixin
from .ui.thumbnails import ThumbnailMixin
from .ui.window_state import WindowStateMixin
from .ui.window_setup import WindowSetupMixin


class MatuwallApp(Adw.Application, NavigationMixin, AppBootstrapMixin, RuntimeMixin, WindowStateMixin, WindowSetupMixin, PanelMixin, ContentMixin, ThumbnailMixin):
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

    @staticmethod
    def _log(message: str) -> None:
        logging.getLogger("matuwall").info(message)

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
