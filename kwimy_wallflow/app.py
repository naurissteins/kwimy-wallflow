from __future__ import annotations

import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .config import AppConfig, load_config
from .paths import APP_ID, ASSETS_DIR, CACHE_DIR
from .ui.navigation import NavigationMixin
from .ui.thumbnails import ThumbnailMixin
from .wallpapers import list_wallpapers


class WallflowApp(Adw.Application, NavigationMixin, ThumbnailMixin):
    LANDSCAPE_RATIO = 9 / 16

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config: AppConfig | None = None
        self._wallpaper_paths: list[Path] = []
        self._load_index = 0
        self._selected_child: Gtk.FlowBoxChild | None = None
        self._selected_index: int = -1
        self._flowbox: Gtk.FlowBox | None = None
        self._scroller: Gtk.ScrolledWindow | None = None
        self._toast_overlay: Adw.ToastOverlay | None = None
        self._scroll_direction: str = "vertical"

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        self.config = load_config()
        self._scroll_direction = (
            self.config.scroll_direction or "vertical"
        ).strip().lower()
        if self._scroll_direction not in {"vertical", "horizontal"}:
            self._scroll_direction = "vertical"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        window = Adw.ApplicationWindow(application=self)
        window.set_default_size(
            int(self.config.window_width), int(self.config.window_height)
        )
        window.set_title("Kwimy Wallflow")
        window.set_decorated(bool(self.config.window_decorations))

        toolbar_view = Adw.ToolbarView()
        if self.config.window_decorations:
            header = Adw.HeaderBar()
            header.set_title_widget(Gtk.Label(label="Kwimy Wallflow"))
            header.add_css_class("wallflow-header")
            toolbar_view.add_top_bar(header)

        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        flowbox.set_activate_on_single_click(True)
        if self._scroll_direction == "horizontal":
            flowbox.set_orientation(Gtk.Orientation.VERTICAL)
        else:
            flowbox.set_orientation(Gtk.Orientation.HORIZONTAL)
        flowbox.set_max_children_per_line(6)
        flowbox.set_column_spacing(12)
        flowbox.set_row_spacing(12)
        flowbox.add_css_class("wallflow-grid")
        self._attach_navigation(flowbox)
        self._flowbox = flowbox

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(flowbox)
        if self._scroll_direction == "horizontal":
            scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        else:
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller = scroller

        toast_overlay = Adw.ToastOverlay()
        toast_overlay.set_child(scroller)
        self._toast_overlay = toast_overlay

        toolbar_view.set_content(toast_overlay)
        window.set_content(toolbar_view)
        window.present()
        flowbox.grab_focus()
        self._init_thumbnail_loader()

        wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
        self._wallpaper_paths = list_wallpapers(wallpaper_dir)
        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

    def _load_css(self) -> None:
        css_path = ASSETS_DIR / "style.css"
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _load_next_batch(self) -> bool:
        if not self._flowbox or not self.config:
            return False

        batch_size = max(1, self.config.batch_size)
        end = min(len(self._wallpaper_paths), self._load_index + batch_size)
        for path in self._wallpaper_paths[self._load_index : end]:
            child = self._build_wallpaper_card(path)
            self._flowbox.append(child)

        self._load_index = end
        return self._load_index < len(self._wallpaper_paths)

    def _run_matugen(self, path: Path) -> None:
        if not self.config:
            return
        try:
            subprocess.Popen(
                [
                    "matugen",
                    "image",
                    str(path),
                    "-m",
                    self.config.matugen_mode,
                    "--source-color-index",
                    "0",
                ]
            )
            self._show_toast(f"Applied {path.name}")
        except FileNotFoundError:
            self._show_toast("matugen not found in PATH")

    def _show_toast(self, message: str) -> None:
        if not self._toast_overlay:
            return
        self._toast_overlay.add_toast(Adw.Toast.new(message))

    def do_shutdown(self) -> None:
        self._shutdown_thumbnail_loader()
        Adw.Application.do_shutdown(self)


def main() -> int:
    app = WallflowApp()
    return app.run([])
