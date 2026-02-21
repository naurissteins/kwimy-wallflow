from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from .config import AppConfig, load_config
from .paths import APP_ID, ASSETS_DIR, CACHE_DIR
from .wallpapers import list_wallpapers


class WallflowApp(Adw.Application):
    LANDSCAPE_RATIO = 9 / 16

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config: AppConfig | None = None
        self._wallpaper_paths: list[Path] = []
        self._load_index = 0
        self._flowbox: Gtk.FlowBox | None = None
        self._toast_overlay: Adw.ToastOverlay | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        self.config = load_config()
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
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(6)
        flowbox.set_column_spacing(12)
        flowbox.set_row_spacing(12)
        flowbox.add_css_class("wallflow-grid")
        self._flowbox = flowbox

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(flowbox)

        toast_overlay = Adw.ToastOverlay()
        toast_overlay.set_child(scroller)
        self._toast_overlay = toast_overlay

        toolbar_view.set_content(toast_overlay)
        window.set_content(toolbar_view)
        window.present()

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

    def _build_wallpaper_card(self, path: Path) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("wallflow-card")
        button.set_focusable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        thumb = self._load_thumbnail(path)
        picture = Gtk.Picture.new_for_paintable(thumb)
        thumb_width, thumb_height = self._thumbnail_dimensions()
        picture.set_size_request(thumb_width, thumb_height)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.add_css_class("wallflow-thumb")

        box.append(picture)
        if self.config.show_filenames:
            label = Gtk.Label(label=path.name)
            label.set_wrap(True)
            label.set_xalign(0.0)
            label.add_css_class("wallflow-label")
            box.append(label)
        button.set_child(box)
        button.connect("clicked", lambda *_: self._run_matugen(path))
        return button

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

    def _load_thumbnail(self, path: Path) -> Gdk.Texture:
        if not self.config:
            return Gdk.Texture.new_for_pixbuf(self._empty_pixbuf())

        thumbnail_path = self._thumbnail_cache_path(path)
        if thumbnail_path.exists():
            try:
                return Gdk.Texture.new_from_file(
                    Gio.File.new_for_path(str(thumbnail_path))
                )
            except Exception:
                pass

        width, height = self._thumbnail_dimensions()
        try:
            pixbuf = self._render_thumbnail(path, width, height)
            pixbuf.savev(str(thumbnail_path), "png", [], [])
            return Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            return Gdk.Texture.new_for_pixbuf(self._empty_pixbuf())

    def _thumbnail_cache_path(self, path: Path) -> Path:
        stat = path.stat()
        width, height = self._thumbnail_dimensions()
        payload = f"{path}-{stat.st_mtime}-{stat.st_size}-{width}x{height}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{digest}.png"

    def _thumbnail_dimensions(self) -> tuple[int, int]:
        width = max(1, self.config.thumbnail_size if self.config else 256)
        shape = (self.config.thumbnail_shape if self.config else "landscape").lower()
        if shape == "square":
            height = width
        else:
            height = max(1, int(width * self.LANDSCAPE_RATIO))
        return width, height

    @staticmethod
    def _empty_pixbuf() -> GdkPixbuf.Pixbuf:
        return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 1, 1)

    @staticmethod
    def _render_thumbnail(path: Path, width: int, height: int) -> GdkPixbuf.Pixbuf:
        base = GdkPixbuf.Pixbuf.new_from_file(str(path))
        src_w = base.get_width()
        src_h = base.get_height()
        if src_w == 0 or src_h == 0:
            return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)

        scale = max(width / src_w, height / src_h)
        scaled_w = max(1, int(src_w * scale))
        scaled_h = max(1, int(src_h * scale))

        scaled = base.scale_simple(
            scaled_w, scaled_h, GdkPixbuf.InterpType.BILINEAR
        )

        if scaled_w == width and scaled_h == height:
            return scaled

        offset_x = max(0, (scaled_w - width) // 2)
        offset_y = max(0, (scaled_h - height) // 2)
        return GdkPixbuf.Pixbuf.new_subpixbuf(
            scaled, offset_x, offset_y, width, height
        )


def main() -> int:
    app = WallflowApp()
    return app.run([])
