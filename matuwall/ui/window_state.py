from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib

from ..config import load_config


class WindowStateMixin:
    _LIVE_THEME_FIELDS = (
        "theme_window_bg",
        "theme_text_color",
        "theme_header_bg_start",
        "theme_header_bg_end",
        "theme_backdrop_bg",
        "theme_card_bg",
        "theme_card_border",
        "theme_card_hover_bg",
        "theme_card_hover_border",
        "theme_card_selected_bg",
        "theme_card_selected_border",
        "theme_window_radius",
        "theme_card_radius",
        "theme_thumb_radius",
    )

    def _refresh_theme_config(self) -> None:
        if not self.config:
            return
        latest = load_config()
        for field in self._LIVE_THEME_FIELDS:
            setattr(self.config, field, getattr(latest, field))
        self._apply_theme_css()

    def _show_window(self) -> None:
        if not self._window:
            return
        if self._window.get_visible():
            return
        self._refresh_theme_config()
        if self._needs_reload:
            self._reload_content()
        # Backdrop click-to-close is intended for panel mode only.
        if self._panel_mode and self._backdrop_enabled:
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
