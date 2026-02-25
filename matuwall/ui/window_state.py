from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib


class WindowStateMixin:
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
