from __future__ import annotations

import hashlib
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

gi.require_version("GdkPixbuf", "2.0")

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GdkPixbuf, Gio, Gtk

from ..paths import CACHE_DIR


class ThumbnailMixin:
    def _build_wallpaper_card(self, path: Path) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("wallflow-card")
        box.set_focusable(False)

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

        child = Gtk.FlowBoxChild()
        child.set_child(box)
        child.wallpaper_path = str(path)
        return child

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
            return GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, True, 8, width, height
            )

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
