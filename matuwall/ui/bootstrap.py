from __future__ import annotations

import argparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

from ..config import css_color_is_fully_transparent
from ..paths import ASSETS_DIR


class AppBootstrapMixin:
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
        css_path = ASSETS_DIR / "style.css"
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _apply_theme_css(self) -> None:
        if not self.config:
            return
        display = Gdk.Display.get_default()
        if not display:
            return
        card_scale = self._card_transform_scale(self.config.thumbnail_size)
        backdrop_bg = self.config.theme_backdrop_bg
        if css_color_is_fully_transparent(backdrop_bg):
            # Fully transparent backdrop can lose click target behavior on
            # some compositors; keep a tiny alpha so outside-click close works.
            backdrop_bg = "rgba(0, 0, 0, 0.01)"
        css = f"""
window {{
    background: {self.config.theme_window_bg};
    color: {self.config.theme_text_color};
    border-radius: {int(self.config.theme_window_radius)}px;
}}

.matuwall-backdrop {{
    background: {backdrop_bg};
}}

.matuwall-header {{
    background: linear-gradient(
        90deg,
        {self.config.theme_header_bg_start},
        {self.config.theme_header_bg_end} 60%
    );
}}

gridview child:selected .matuwall-card {{
    border-color: {self.config.theme_card_selected_border};
    background: {self.config.theme_card_selected_bg};
    transform: scale({card_scale});
}}

gridview child:hover .matuwall-card {{
    border-color: {self.config.theme_card_hover_border};
    background: {self.config.theme_card_hover_bg};
    transform: scale({card_scale});
}}

.matuwall-card {{
    background: {self.config.theme_card_bg};
    border-color: {self.config.theme_card_border};
    border-radius: {int(self.config.theme_card_radius)}px;
}}

.matuwall-thumb {{
    border-radius: {int(self.config.theme_thumb_radius)}px;
}}
"""
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css.encode("utf-8"))
        except Exception:
            return
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2
        )
        self._theme_css_provider = provider

    @staticmethod
    def _card_transform_scale(thumbnail_size: int) -> str:
        size = max(1, int(thumbnail_size))
        if size <= 300:
            return "1.09"
        if size <= 500:
            return "1.05"
        if size <= 800:
            return "1.03"
        return "1.02"
