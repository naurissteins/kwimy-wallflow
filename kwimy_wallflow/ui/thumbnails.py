from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from ..paths import CACHE_DIR


class ThumbnailMixin:
    def _init_thumbnail_loader(self) -> None:
        if getattr(self, "_thumb_executor", None) is not None:
            return
        self._thumb_executor = ThreadPoolExecutor(max_workers=2)
        self._thumb_waiters: dict[str, list[tuple[Gtk.Picture, Gtk.Spinner]]] = {}
        self._thumb_futures = {}

    def _shutdown_thumbnail_loader(self) -> None:
        executor = getattr(self, "_thumb_executor", None)
        if executor is not None:
            executor.shutdown(wait=False)
            self._thumb_executor = None

    def _build_wallpaper_card(self, path: Path) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("wallflow-card")
        box.set_focusable(False)

        thumb, cached = self._load_thumbnail_cached(path)
        picture = Gtk.Picture.new_for_paintable(thumb)
        thumb_width, thumb_height = self._thumbnail_dimensions()
        picture.set_size_request(thumb_width, thumb_height)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.add_css_class("wallflow-thumb")

        thumb_overlay = Gtk.Overlay()
        thumb_overlay.set_child(picture)

        spinner = Gtk.Spinner()
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        spinner.add_css_class("wallflow-thumb-spinner")
        spinner.set_visible(False)
        thumb_overlay.add_overlay(spinner)

        box.append(thumb_overlay)
        if self.config.show_filenames:
            label = Gtk.Label(label=path.name)
            label.set_wrap(True)
            label.set_xalign(0.0)
            label.add_css_class("wallflow-label")
            box.append(label)

        child = Gtk.FlowBoxChild()
        child.set_child(box)
        child.wallpaper_path = str(path)

        if not cached:
            spinner.set_visible(True)
            spinner.start()
            self._queue_thumbnail_load(path, picture, spinner)

        return child

    def _load_thumbnail_cached(self, path: Path) -> tuple[Gdk.Texture, bool]:
        if not self.config:
            return Gdk.Texture.new_for_pixbuf(self._empty_pixbuf()), True

        thumbnail_path = self._thumbnail_cache_path(path)
        if thumbnail_path.exists():
            try:
                return (
                    Gdk.Texture.new_from_file(Gio.File.new_for_path(str(thumbnail_path))),
                    True,
                )
            except Exception:
                pass

        return Gdk.Texture.new_for_pixbuf(self._empty_pixbuf()), False

    def _queue_thumbnail_load(
        self, path: Path, picture: Gtk.Picture, spinner: Gtk.Spinner
    ) -> None:
        executor = getattr(self, "_thumb_executor", None)
        if executor is None:
            return

        key = str(path)
        waiters = self._thumb_waiters.setdefault(key, [])
        waiters.append((picture, spinner))

        if key in self._thumb_futures:
            return

        future = executor.submit(self._generate_thumbnail_file, path)
        self._thumb_futures[key] = future
        future.add_done_callback(
            lambda fut, key=key: GLib.idle_add(self._apply_thumbnail_result, key, fut)
        )

    def _apply_thumbnail_result(self, key: str, future) -> bool:
        self._thumb_futures.pop(key, None)

        try:
            thumbnail_path = future.result()
        except Exception:
            thumbnail_path = None

        waiters = self._thumb_waiters.pop(key, [])
        if waiters:
            for picture, spinner in waiters:
                if thumbnail_path:
                    self._set_picture_from_file(picture, thumbnail_path)
                spinner.stop()
                spinner.set_visible(False)
        return False

    def _set_picture_from_file(self, picture: Gtk.Picture, path: Path) -> None:
        try:
            picture.set_paintable(
                Gdk.Texture.new_from_file(Gio.File.new_for_path(str(path)))
            )
        except Exception:
            return

    def _generate_thumbnail_file(self, path: Path) -> Path | None:
        if not self.config:
            return None
        thumbnail_path = self._thumbnail_cache_path(path)
        if thumbnail_path.exists():
            return thumbnail_path

        width, height = self._thumbnail_dimensions()
        try:
            pixbuf = self._render_thumbnail(path, width, height)
            pixbuf.savev(str(thumbnail_path), "png", [], [])
            return thumbnail_path
        except Exception:
            return None

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
