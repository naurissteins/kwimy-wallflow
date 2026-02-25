from __future__ import annotations

import hashlib
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from ..paths import CACHE_DIR


LOGGER = logging.getLogger("matuwall.thumbnails")


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

    def _build_wallpaper_card_widget(self, path: Path) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("matuwall-card")

        thumb, cached = self._load_thumbnail_cached(path)
        picture = Gtk.Picture.new_for_paintable(thumb)
        thumb_width, thumb_height = self._thumbnail_dimensions()
        picture.set_size_request(thumb_width, thumb_height)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.add_css_class("matuwall-thumb")

        thumb_overlay = Gtk.Overlay()
        thumb_overlay.set_child(picture)

        spinner = Gtk.Spinner()
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        spinner.add_css_class("matuwall-thumb-spinner")
        spinner.set_visible(False)
        thumb_overlay.add_overlay(spinner)

        box.append(thumb_overlay)
        # Filenames are intentionally hidden.

        if self._panel_full_width_enabled():
            box.set_hexpand(True)
            box.set_halign(Gtk.Align.FILL)
            thumb_overlay.set_hexpand(True)
            thumb_overlay.set_halign(Gtk.Align.FILL)
            picture.set_hexpand(True)
            picture.set_halign(Gtk.Align.FILL)
        
        if self.config and not self.config.mouse_enabled:
            box.set_can_target(False)

        if not cached:
            spinner.set_visible(True)
            spinner.start()
            self._queue_thumbnail_load(path, picture, spinner)

        return box

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
            if not thumbnail_path.exists():
                raise RuntimeError("thumbnail save produced no file")
            if thumbnail_path.stat().st_size == 0:
                try:
                    thumbnail_path.unlink()
                except OSError:
                    pass
                raise RuntimeError("thumbnail save produced empty file")
            return thumbnail_path
        except GLib.Error as exc:
            self._log_thumbnail_error(path, exc)
            return None
        except Exception as exc:
            self._log_thumbnail_error(path, exc)
            return None

    def _thumbnail_cache_path(self, path: Path) -> Path:
        try:
            stat = path.stat()
            stat_key = f"{stat.st_mtime}-{stat.st_size}"
        except Exception:
            stat_key = "nostat"
        width, height = self._thumbnail_dimensions()
        payload = f"{path}-{stat_key}-{width}x{height}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{digest}.png"

    def _thumbnail_dimensions(self) -> tuple[int, int]:
        resolver = getattr(self, "_thumb_dimensions_for_layout", None)
        if callable(resolver):
            return resolver()

        width = max(1, self.config.thumbnail_size if self.config else 256)
        if self._panel_full_width_enabled():
            # Match default CSS: grid padding 16px left/right, card padding 8px.
            available = int(getattr(self, "_panel_size", width))
            available -= getattr(self, "GRID_PADDING", 16) * 2
            full_width = max(1, available - getattr(self, "CARD_PADDING", 8) * 2)
            width = max(1, full_width)
        shape = (self.config.thumbnail_shape if self.config else "landscape").lower()
        if shape == "square":
            height = width
        else:
            height = max(1, int(width * self.LANDSCAPE_RATIO))
        return width, height

    def _panel_full_width_enabled(self) -> bool:
        if not self.config:
            return False
        if not getattr(self, "_panel_mode", False):
            return False
        edge = str(getattr(self, "_panel_edge", "left")).lower()
        return edge in {"left", "right"} and self._scroll_direction == "vertical"

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
        scaled_w = max(1, int(math.ceil(src_w * scale)))
        scaled_h = max(1, int(math.ceil(src_h * scale)))

        scaled = base.scale_simple(
            scaled_w, scaled_h, GdkPixbuf.InterpType.BILINEAR
        )
        if scaled is None:
            return GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, True, 8, width, height
            )

        if scaled_w == width and scaled_h == height:
            return scaled
        if scaled_w < width or scaled_h < height:
            # Fallback: stretch to requested size if rounding got too small.
            stretched = scaled.scale_simple(
                width, height, GdkPixbuf.InterpType.BILINEAR
            )
            if stretched is None:
                return GdkPixbuf.Pixbuf.new(
                    GdkPixbuf.Colorspace.RGB, True, 8, width, height
                )
            return stretched

        offset_x = max(0, (scaled_w - width) // 2)
        offset_y = max(0, (scaled_h - height) // 2)
        cropped = GdkPixbuf.Pixbuf.new_subpixbuf(
            scaled, offset_x, offset_y, width, height
        )
        if cropped is None:
            return scaled
        return cropped

    def _log_thumbnail_error(self, path: Path, exc: Exception) -> None:
        logger = getattr(self, "_log", None)
        message = f"Thumbnail failed for {path}: {exc}"
        if callable(logger):
            logger(message)
        else:
            LOGGER.error(message)
