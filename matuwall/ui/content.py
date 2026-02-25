from __future__ import annotations

import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ..wallpapers import list_wallpapers
from .models import WallpaperItem


class ContentMixin:
    def _load_next_batch(self) -> bool:
        if self._list_store is None or not self.config:
            return False

        batch_size = max(1, self.config.batch_size)
        end = min(len(self._wallpaper_paths), self._load_index + batch_size)
        for path in self._wallpaper_paths[self._load_index : end]:
            self._list_store.append(WallpaperItem(path))

        self._load_index = end
        if self._load_index < len(self._wallpaper_paths):
            GLib.idle_add(self._load_next_batch)
        return False

    def _reload_content(self) -> None:
        self._needs_reload = False
        if not self.config:
            return
        self._init_thumbnail_loader()
        if self._list_store:
            self._list_store.remove_all()

        wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
        if not wallpaper_dir.exists():
            if self._scroller:
                self._scroller.set_child(
                    self._build_empty_state(
                        "Wallpaper folder not found",
                        f"{wallpaper_dir}\nSet a valid path in ~/.config/matuwall/config.json",
                    )
                )
            self._grid_view = None
            return

        self._wallpaper_paths = list_wallpapers(wallpaper_dir)
        if not self._wallpaper_paths:
            if self._scroller:
                self._scroller.set_child(
                    self._build_empty_state(
                        "No wallpapers found",
                        f"Add images to {wallpaper_dir}\nSupported: jpg, jpeg, png, webp, bmp, gif",
                    )
                )
            self._grid_view = None
            return

        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

    @staticmethod
    def _build_empty_state(title: str, subtitle: str) -> Gtk.Widget:
        page = Adw.StatusPage()
        page.set_title(title)
        page.set_description(subtitle)
        page.add_css_class("matuwall-empty")
        page.set_hexpand(True)
        page.set_vexpand(True)
        return page

    def _build_content(self) -> None:
        if not self._window or not self.config:
            return
        toolbar_view = Adw.ToolbarView()
        if self.config.window_decorations:
            header = Adw.HeaderBar()
            header.set_title_widget(Gtk.Label(label="Matuwall"))
            header.add_css_class("matuwall-header")
            toolbar_view.add_top_bar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.add_css_class("matuwall-scroller")
        if self._scroll_direction == "horizontal":
            scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        else:
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._hide_scrollbars(scroller)
        self._scroller = scroller

        if not self.config.mouse_enabled:
            scroller.set_can_target(False)
        scroller.set_can_focus(True)

        toast_overlay = Adw.ToastOverlay()
        toast_overlay.set_child(scroller)
        self._toast_overlay = toast_overlay

        toolbar_view.set_content(toast_overlay)
        self._window.set_content(toolbar_view)

        wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
        if not wallpaper_dir.exists():
            self._grid_view = None
            self._wallpaper_paths = []
            scroller.set_child(
                self._build_empty_state(
                    "Wallpaper folder not found",
                    f"{wallpaper_dir}\nSet a valid path in ~/.config/matuwall/config.json",
                )
            )
            return

        self._wallpaper_paths = list_wallpapers(wallpaper_dir)
        if not self._wallpaper_paths:
            self._grid_view = None
            scroller.set_child(
                self._build_empty_state(
                    "No wallpapers found",
                    f"Add images to {wallpaper_dir}\nSupported: jpg, jpeg, png, webp, bmp, gif",
                )
            )
            return
        self._log(f"wallpapers found: {len(self._wallpaper_paths)} in {wallpaper_dir}")

        self._list_store = Gio.ListStore.new(WallpaperItem)
        selection_model = Gtk.SingleSelection.new(self._list_store)
        selection_model.connect("notify::selected", self._on_selection_changed_snap)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)

        grid_view = Gtk.GridView(model=selection_model, factory=factory)
        if self._scroll_direction == "horizontal":
            grid_view.set_orientation(Gtk.Orientation.HORIZONTAL)
        else:
            grid_view.set_orientation(Gtk.Orientation.VERTICAL)

        grid_view.set_valign(Gtk.Align.START)
        grid_view.set_halign(Gtk.Align.FILL)
        grid_view.add_css_class("matuwall-grid")

        if not self._panel_mode and self.config:
            cols = max(1, int(self.config.window_grid_cols))
            grid_view.set_min_columns(cols)
            grid_view.set_max_columns(cols)
            grid_view.set_enable_rubberband(True)

        if (
            self._panel_mode
            and self._scroll_direction == "vertical"
            and self._panel_edge in {"left", "right"}
        ):
            grid_view.set_max_columns(1)
            grid_view.set_min_columns(1)
            grid_view.set_halign(Gtk.Align.FILL)
            grid_view.set_hexpand(True)

        grid_view.connect("activate", self._on_grid_item_activated)
        self._attach_navigation(grid_view)

        self._grid_view = grid_view
        viewport_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL
            if self._scroll_direction != "horizontal"
            else Gtk.Orientation.HORIZONTAL
        )
        viewport_box.set_valign(Gtk.Align.START)
        viewport_box.set_halign(Gtk.Align.FILL)
        viewport_box.set_hexpand(True)
        viewport_box.set_vexpand(True)
        viewport_box.add_css_class("matuwall-viewport")
        viewport_box.append(grid_view)
        scroller.set_child(viewport_box)

        if not self.config.mouse_enabled:
            grid_view.set_can_target(False)

        self._init_thumbnail_loader()
        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

    def _on_factory_setup(self, _factory, list_item: Gtk.ListItem) -> None:
        # We'll build the widget in bind because we need the path
        pass

    def _on_factory_bind(self, _factory, list_item: Gtk.ListItem) -> None:
        item = list_item.get_item()
        if not item:
            return
        widget = self._build_wallpaper_card_widget(item.path)
        list_item.set_child(widget)
        # Handle selection visual state via CSS on GtkListItem

    def _on_selection_changed_snap(self, model: Gtk.SingleSelection, _pspec) -> None:
        if not self._scroller or not self.config:
            return

        index = model.get_selected()
        if index == Gtk.INVALID_LIST_POSITION:
            return

        is_horiz = self._scroll_direction == "horizontal"

        # How many rows/cols we want to see
        if self._panel_mode:
            visible_count = max(1, int(self._panel_thumbs_col))
        else:
            visible_count = max(1, int(self.config.window_grid_rows if not is_horiz else self.config.window_grid_cols))

        item_outer_width, item_outer_height = self._get_item_outer_dimensions()

        adj = self._scroller.get_hadjustment() if is_horiz else self._scroller.get_vadjustment()
        if not adj:
            return

        item_size = item_outer_width if is_horiz else item_outer_height
        current_vscroll = adj.get_value()

        # In GridView panel mode, cols is always 1 in the non-scrolling direction
        # In window mode, it's grid_cols
        if self._panel_mode:
            pos = index
        else:
            cols = max(1, int(self.config.window_grid_cols if not is_horiz else self.config.window_grid_rows))
            pos = index // cols

        top_item = int(current_vscroll // item_size)
        bottom_item = top_item + visible_count - 1

        target_vscroll = current_vscroll

        if pos < top_item:
            target_vscroll = pos * item_size
        elif pos > bottom_item:
            target_vscroll = (pos - visible_count + 1) * item_size

        if target_vscroll != current_vscroll:
            if self._snap_anim:
                self._snap_anim.pause()

            target_vscroll = max(0, min(target_vscroll, adj.get_upper() - adj.get_page_size()))

            target = Adw.CallbackAnimationTarget.new(adj.set_value)
            self._snap_anim = Adw.TimedAnimation.new(
                self._scroller,
                current_vscroll,
                target_vscroll,
                250,
                target
            )
            self._snap_anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
            self._snap_anim.play()

    def _on_grid_item_activated(self, _grid_view, position: int) -> None:
        if self._list_store:
            item = self._list_store.get_item(position)
            if item:
                self._run_matugen(item.path)

    def _run_matugen(self, path: Path) -> None:
        if not self.config:
            return
        try:
            env = os.environ.copy()
            env.pop("LD_PRELOAD", None)
            env.pop("GDK_BACKEND", None)
            subprocess.Popen(
                [
                    "matugen",
                    "image",
                    str(path),
                    "-m",
                    self.config.matugen_mode,
                    "--source-color-index",
                    "0",
                ],
                env=env,
            )
            self._show_toast(f"Applied {path.name}")
        except FileNotFoundError:
            self._show_toast("matugen not found in PATH")

    def _show_toast(self, message: str) -> None:
        if not self._toast_overlay:
            return
        self._toast_overlay.add_toast(Adw.Toast.new(message))

    def _hide_scrollbars(self, scroller: Gtk.ScrolledWindow) -> None:
        scroller.add_css_class("matuwall-hide-scrollbar")
        if self._scrollbar_css_applied:
            return
        display = Gdk.Display.get_default()
        if not display:
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
.matuwall-hide-scrollbar scrollbar {
    opacity: 0;
    min-width: 0;
    min-height: 0;
    margin: 0;
}
.matuwall-hide-scrollbar scrollbar slider {
    min-width: 0;
    min-height: 0;
}
"""
        )
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self._scrollbar_css_applied = True
