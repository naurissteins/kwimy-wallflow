from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ..paths import IPC_SOCKET_PATH
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
        self._reset_applied_badges()
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
        self._reset_applied_badges()
        toolbar_view = Adw.ToolbarView()
        if not self._panel_mode and self.config.window_decorations:
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

        # Track the last known stable scroll position to prevent jumps
        self._last_stable_vscroll = 0.0
        adj = scroller.get_hadjustment() if self._scroll_direction == "horizontal" else scroller.get_vadjustment()
        if adj:
            adj.connect("value-changed", self._on_scroll_value_changed)

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

        grid_view.set_halign(Gtk.Align.FILL)
        grid_view.add_css_class("matuwall-grid")
        grid_view.add_css_class("matuwall-viewport")

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
        scroller.set_child(grid_view)

        if not self.config.mouse_enabled:
            grid_view.set_can_target(False)

        self._init_thumbnail_loader()
        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

    def _on_scroll_value_changed(self, adj: Gtk.Adjustment) -> None:
        if self._is_keyboard_navigating:
            # During keyboard navigation, ignore the automatic jumps
            # handle the scroll in _on_selection_changed_snap
            pass
        elif self._snap_anim and self._snap_anim.get_state() == Adw.AnimationState.PLAYING:
            # During our own animation, don't update the stable position
            pass
        else:
            # Normal user scroll (mouse/touchpad), update stable position
            self._last_stable_vscroll = adj.get_value()

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
            self._is_keyboard_navigating = False
            return

        index = model.get_selected()
        if index == Gtk.INVALID_LIST_POSITION:
            self._is_keyboard_navigating = False
            return

        is_horiz = self._scroll_direction == "horizontal"

        # How many rows/cols we want to see
        if self._panel_mode:
            visible_count = max(1, int(self._panel_thumbs_col))
        else:
            visible_count = max(
                1,
                int(self.config.window_grid_rows if not is_horiz else self.config.window_grid_cols),
            )

        item_outer_width, item_outer_height = self._get_item_outer_dimensions()

        adj = self._scroller.get_hadjustment() if is_horiz else self._scroller.get_vadjustment()
        if not adj:
            self._is_keyboard_navigating = False
            return

        item_size = item_outer_width if is_horiz else item_outer_height
        
        # Capture current scroll position and determine the animation starting point.
        # If we just performed a keyboard move, we want to animate from the 
        # position we WERE at, not where GTK might have jumped
        current_vscroll = adj.get_value()
        start_vscroll = self._last_stable_vscroll if self._is_keyboard_navigating else current_vscroll
        
        # Reset flag now that captured the animation context
        is_kb = self._is_keyboard_navigating
        self._is_keyboard_navigating = False

        # Calculate the index position in the scrolling direction
        if self._panel_mode:
            pos = index
        else:
            cols = max(
                1,
                int(self.config.window_grid_cols if not is_horiz else self.config.window_grid_rows),
            )
            pos = index // cols

        # Calculate the ideal target positions for snapping (top or bottom)
        item_top_position = pos * item_size
        item_bottom_position = (pos - visible_count + 1) * item_size

        target_vscroll = start_vscroll

        # Define the currently visible range based on the start position
        view_top = start_vscroll
        view_bottom = start_vscroll + (visible_count * item_size)

        # Determine if we need to scroll to bring the item into view
        if pos * item_size < view_top + 0.5:
            target_vscroll = item_top_position
        elif (pos + 1) * item_size > view_bottom - 0.5:
            target_vscroll = item_bottom_position

        if is_kb or abs(target_vscroll - current_vscroll) > 0.5:
            if self._snap_anim:
                self._snap_anim.pause()
                self._snap_anim = None

            target_vscroll = max(0, min(target_vscroll, adj.get_upper() - adj.get_page_size()))
            
            # If the value has already changed (GTK jump), force it back to 
            # the start position before initiating the animation to avoid flicker
            if is_kb and abs(current_vscroll - start_vscroll) > 0.5:
                adj.set_value(start_vscroll)

            if abs(target_vscroll - start_vscroll) > 0.5:
                target = Adw.CallbackAnimationTarget.new(adj.set_value)
                self._snap_anim = Adw.TimedAnimation.new(
                    self._scroller, start_vscroll, target_vscroll, 200, target
                )
                self._snap_anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
                self._snap_anim.play()
        
        self._last_stable_vscroll = target_vscroll

    def _on_grid_item_activated(self, _grid_view, position: int) -> None:
        if self._list_store:
            item = self._list_store.get_item(position)
            if item:
                self._run_matugen(item.path)

    def _run_matugen(self, path: Path) -> None:
        if not self.config:
            return
        if self.config.wall_mode_only:
            self._run_awww(path)
            return
        self._run_matugen_image(path)

    def _run_matugen_image(self, path: Path) -> None:
        if not self.config:
            return
        if shutil.which("matugen") is None:
            self._report_apply_issue("matugen not found")
            self._show_toast("matugen not found in PATH")
            return
        command = [
            "matugen",
            "image",
            str(path),
            "-m",
            self.config.matugen_mode,
            "-t",
            self.config.matugen_type,
            "--source-color-index",
            "0",
        ]
        if self.config.matugen_contrast is not None:
            command.extend(["--contrast", str(self.config.matugen_contrast)])
        try:
            env = os.environ.copy()
            env.pop("LD_PRELOAD", None)
            env.pop("GDK_BACKEND", None)
            subprocess.Popen(command, env=env)
            self._report_apply_command(command)
            if not self._show_applied_overlay(path):
                self._show_toast("Applied")
        except FileNotFoundError:
            self._report_apply_issue("matugen not found")
            self._show_toast("matugen not found in PATH")

    def _run_awww(self, path: Path) -> None:
        if not self.config:
            return
        try:
            flags = shlex.split(self.config.wall_awww_flags) if self.config.wall_awww_flags else []
        except ValueError:
            self._report_apply_issue("invalid wall_awww_flags")
            self._show_toast("Invalid wall_awww_flags")
            return
        if shutil.which("awww") is None:
            self._report_apply_issue("awww not found")
            self._show_toast("awww not found in PATH")
            return
        if not self._is_process_running("awww-daemon"):
            self._report_apply_issue("awww-daemon is not running")
            self._show_toast("awww-daemon is not running")
            return
        command = [
            "awww",
            "img",
            *flags,
            str(path),
        ]
        try:
            env = os.environ.copy()
            env.pop("LD_PRELOAD", None)
            env.pop("GDK_BACKEND", None)
            subprocess.Popen(command, env=env)
            self._report_apply_command(command)
            if not self._show_applied_overlay(path):
                self._show_toast("Applied")
        except FileNotFoundError:
            self._report_apply_issue("awww not found")
            self._show_toast("awww not found in PATH")

    @staticmethod
    def _report_apply_log(message: str) -> None:
        payload = f"log {message}".encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(str(IPC_SOCKET_PATH))
                sock.send(payload)
        except OSError:
            return

    @staticmethod
    def _report_apply_command(command: list[str]) -> None:
        ContentMixin._report_apply_log(f"[apply-cmd] {shlex.join(command)}")

    @staticmethod
    def _report_apply_issue(issue: str) -> None:
        ContentMixin._report_apply_log(f"[apply-cmd] {issue}")

    @staticmethod
    def _is_process_running(process_name: str) -> bool:
        proc_root = Path("/proc")
        try:
            proc_entries = proc_root.iterdir()
        except OSError:
            return False

        process_name_bytes = process_name.encode()
        for entry in proc_entries:
            if not entry.name.isdigit():
                continue
            comm_path = entry / "comm"
            try:
                if comm_path.read_text(encoding="utf-8").strip() == process_name:
                    return True
            except OSError:
                pass

            cmdline_path = entry / "cmdline"
            try:
                cmdline = cmdline_path.read_bytes()
            except OSError:
                continue
            if process_name_bytes in cmdline:
                return True
        return False

    def _show_toast(self, message: str) -> None:
        if not self._toast_overlay:
            return
        self._toast_overlay.add_toast(Adw.Toast.new(message))

    def _reset_applied_badges(self) -> None:
        source_ids = getattr(self, "_applied_badge_timeout_ids", {})
        for source_id in source_ids.values():
            try:
                GLib.source_remove(source_id)
            except Exception:
                pass
        self._applied_badges: dict[str, list[Gtk.Widget]] = {}
        self._applied_badge_timeout_ids: dict[int, int] = {}

    def _register_applied_badge(self, path: Path, badge: Gtk.Widget) -> None:
        if not hasattr(self, "_applied_badges"):
            self._applied_badges = {}
        key = str(path)
        badges = self._applied_badges.setdefault(key, [])
        badges.append(badge)

    def _show_applied_overlay(self, path: Path) -> bool:
        badges_by_path: dict[str, list[Gtk.Widget]] = getattr(self, "_applied_badges", {})
        timeout_ids: dict[int, int] = getattr(self, "_applied_badge_timeout_ids", {})
        key = str(path)
        badges = badges_by_path.get(key, [])
        if not badges:
            return False

        active_badges: list[Gtk.Widget] = []
        for badge in badges:
            if badge.get_parent() is None:
                continue
            badge.set_visible(True)
            badge.add_css_class("matuwall-applied-overlay-visible")

            badge_id = id(badge)
            previous_source_id = timeout_ids.pop(badge_id, None)
            if previous_source_id is not None:
                try:
                    GLib.source_remove(previous_source_id)
                except Exception:
                    pass

            source_id = GLib.timeout_add(900, self._hide_applied_overlay, badge)
            timeout_ids[badge_id] = source_id
            active_badges.append(badge)

        if not active_badges:
            return False

        badges_by_path[key] = active_badges
        return True

    def _hide_applied_overlay(self, badge: Gtk.Widget) -> bool:
        badge.remove_css_class("matuwall-applied-overlay-visible")
        badge.set_visible(False)
        timeout_ids: dict[int, int] = getattr(self, "_applied_badge_timeout_ids", {})
        timeout_ids.pop(id(badge), None)
        return False

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
