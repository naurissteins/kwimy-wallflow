from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

LAYER_SHELL_ERROR = None
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell  # type: ignore
except (ImportError, ValueError) as exc:
    LayerShell = None
    LAYER_SHELL_ERROR = str(exc)

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .config import AppConfig, load_config
from .paths import APP_ID, ASSETS_DIR, CACHE_DIR
from .ui.navigation import NavigationMixin
from .ui.thumbnails import ThumbnailMixin
from .wallpapers import list_wallpapers


class WallflowApp(Adw.Application, NavigationMixin, ThumbnailMixin):
    LANDSCAPE_RATIO = 9 / 16

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config: AppConfig | None = None
        self._wallpaper_paths: list[Path] = []
        self._load_index = 0
        self._selected_child: Gtk.FlowBoxChild | None = None
        self._selected_index: int = -1
        self._flowbox: Gtk.FlowBox | None = None
        self._scroller: Gtk.ScrolledWindow | None = None
        self._toast_overlay: Adw.ToastOverlay | None = None
        self._window: Adw.ApplicationWindow | None = None
        self._scroll_direction: str = "vertical"
        self._panel_mode = False
        self._panel_edge: str = "left"
        self._panel_size: int = 420
        self._panel_fit: bool = True
        self._daemon_enabled = False
        self._daemon_start_hidden = False
        self._pending_action: str | None = None
        self._quit_requested = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        if LAYER_SHELL_ERROR:
            self._log(f"gtk4-layer-shell import error: {LAYER_SHELL_ERROR}")

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = list(command_line.get_arguments())
        opts = self._parse_args([str(a) for a in args[1:]])

        if opts.daemon:
            self._daemon_enabled = True
            self._daemon_start_hidden = True
            self.hold()

        if opts.quit:
            self._quit_requested = True

        if opts.toggle:
            self._pending_action = "toggle"
        elif opts.show:
            self._pending_action = "show"
        elif opts.hide:
            self._pending_action = "hide"

        self.activate()
        return 0

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
        self._ensure_window()

        if self._quit_requested:
            self.quit()
            return

        if self._pending_action == "toggle":
            if self._window and self._window.get_visible():
                self._window.hide()
            else:
                self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "show":
            self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "hide":
            if self._window:
                self._window.hide()
            self._pending_action = None
            return

        if self._daemon_start_hidden:
            self._daemon_start_hidden = False
            return

        self._show_window()

    def _show_window(self) -> None:
        if not self._window:
            return
        self._window.present()
        if self._flowbox:
            self._flowbox.grab_focus()
        if self._panel_mode:
            GLib.idle_add(self._refresh_layer_shell)

    def _refresh_layer_shell(self) -> bool:
        if not self._panel_mode or not self._window:
            return False
        self._apply_layer_shell(
            self._window, self._panel_edge, self._panel_size, self._panel_fit
        )
        return False

    def _ensure_window(self) -> None:
        if self._window:
            return

        self.config = load_config()
        self._scroll_direction = (
            self.config.scroll_direction or "vertical"
        ).strip().lower()
        if self._scroll_direction not in {"vertical", "horizontal"}:
            self._scroll_direction = "vertical"
        self._panel_mode = bool(self.config.panel_mode and LayerShell is not None)
        if self._panel_mode and not self._is_wayland():
            self._panel_mode = False
            self._log("Layer-shell requires Wayland; panel_mode disabled")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        window = Adw.ApplicationWindow(application=self)
        panel_edge = str(self.config.panel_edge).strip().lower()
        if panel_edge not in {"left", "right", "top", "bottom"}:
            panel_edge = "left"
        panel_size = max(1, int(self.config.panel_size))
        panel_fit = bool(self.config.panel_fit_to_screen)
        self._panel_edge = panel_edge
        self._panel_size = panel_size
        self._panel_fit = panel_fit
        if self._panel_mode:
            monitor_width, monitor_height = self._get_primary_monitor_size()
            target_width, target_height = self._panel_target_size(
                panel_edge,
                panel_size,
                panel_fit,
                monitor_width,
                monitor_height,
            )
            window.set_default_size(target_width, target_height)
            window.set_decorated(False)
            window.set_resizable(False)
        else:
            window.set_default_size(
                int(self.config.window_width), int(self.config.window_height)
            )
        window.set_title("Kwimy Wallflow")
        if not self._panel_mode:
            window.set_decorated(bool(self.config.window_decorations))
        window.connect("close-request", self._on_close_request)
        self._window = window
        if self.config.panel_mode and LayerShell is None:
            self._log("gtk4-layer-shell not available; panel_mode disabled")
        if self._panel_mode:
            self._apply_layer_shell(window, panel_edge, panel_size, panel_fit)
        if self._panel_mode:
            self._log(
                "panel_mode=%s edge=%s size=%s fit=%s backend=%s target=%sx%s"
                % (
                    self._panel_mode,
                    panel_edge,
                    panel_size,
                    panel_fit,
                    (
                        Gdk.Display.get_default().get_name()
                        if Gdk.Display.get_default()
                        else "none"
                    ),
                    target_width,
                    target_height,
                )
            )
        else:
            self._log(
                "panel_mode=%s edge=%s size=%s fit=%s backend=%s"
                % (
                    self._panel_mode,
                    panel_edge,
                    panel_size,
                    panel_fit,
                    (
                        Gdk.Display.get_default().get_name()
                        if Gdk.Display.get_default()
                        else "none"
                    ),
                )
            )

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

        self._init_thumbnail_loader()
        wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
        self._wallpaper_paths = list_wallpapers(wallpaper_dir)
        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self._daemon_enabled:
            if self._window:
                self._window.hide()
            return True
        return False

    @staticmethod
    def _is_wayland() -> bool:
        display = Gdk.Display.get_default()
        if not display:
            return False
        name = (display.get_name() or "").lower()
        if "wayland" in name:
            return True
        return False

    def _apply_layer_shell(
        self, window: Gtk.Window, panel_edge: str, panel_size: int, fit_to_screen: bool
    ) -> None:
        if LayerShell is None:
            return
        LayerShell.init_for_window(window)
        try:
            LayerShell.set_namespace(window, "kwimy-wallflow")
        except Exception:
            pass
        try:
            if hasattr(LayerShell, "is_supported") and not LayerShell.is_supported():
                self._log("gtk4-layer-shell reports unsupported; trying anyway")
        except Exception:
            pass
        self._log("layer_shell init called")
        try:
            if hasattr(LayerShell, "is_layer_window"):
                self._log(f"layer_shell active: {LayerShell.is_layer_window(window)}")
        except Exception:
            pass
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.ON_DEMAND)
        LayerShell.set_exclusive_zone(
            window, int(self.config.panel_exclusive_zone)
        )

        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, False)
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, False)
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, False)
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, False)

        monitor_width, monitor_height = self._get_primary_monitor_size()
        self._log(
            "layer_shell monitor size: %sx%s" % (monitor_width, monitor_height)
        )

        target_width, target_height = self._panel_target_size(
            panel_edge,
            panel_size,
            fit_to_screen,
            monitor_width,
            monitor_height,
        )

        if panel_edge == "left":
            LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
            LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
            if fit_to_screen:
                LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
                self._set_layer_size(window, target_width, target_height)
            else:
                self._set_layer_size(window, target_width, target_height)
        elif panel_edge == "right":
            LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
            LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
            if fit_to_screen:
                LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
                self._set_layer_size(window, target_width, target_height)
            else:
                self._set_layer_size(window, target_width, target_height)
        elif panel_edge == "top":
            LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
            if fit_to_screen:
                LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
                self._set_layer_size(window, target_width, target_height)
            else:
                self._set_layer_size(window, target_width, target_height)
        else:
            LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
            if fit_to_screen:
                LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
                self._set_layer_size(window, target_width, target_height)
            else:
                self._set_layer_size(window, target_width, target_height)
        self._apply_panel_size_hint(window, target_width, target_height)

    def _set_layer_size(self, window: Gtk.Window, width: int, height: int) -> None:
        if LayerShell is None:
            return
        try:
            LayerShell.set_size(window, int(width), int(height))
        except Exception:
            return

    @staticmethod
    def _panel_target_size(
        panel_edge: str,
        panel_size: int,
        fit_to_screen: bool,
        monitor_width: int,
        monitor_height: int,
    ) -> tuple[int, int]:
        if panel_edge in {"left", "right"}:
            width = panel_size
            height = monitor_height if fit_to_screen and monitor_height else 1
        else:
            width = monitor_width if fit_to_screen and monitor_width else 1
            height = panel_size
        return int(width), int(height)

    @staticmethod
    def _apply_panel_size_hint(
        window: Gtk.Window, width: int, height: int
    ) -> None:
        if width > 0 and height > 0:
            try:
                window.set_default_size(int(width), int(height))
            except Exception:
                pass
            try:
                window.set_size_request(int(width), int(height))
            except Exception:
                pass
    @staticmethod
    def _get_primary_monitor_size() -> tuple[int, int]:
        display = Gdk.Display.get_default()
        if not display:
            return 0, 0
        monitor = None
        if hasattr(display, "get_primary_monitor"):
            try:
                monitor = display.get_primary_monitor()
            except Exception:
                monitor = None
        if monitor is None:
            monitors = display.get_monitors()
            if monitors and monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
        if monitor is None:
            return 0, 0
        geometry = monitor.get_geometry()
        return int(geometry.width), int(geometry.height)

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

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)

    def do_shutdown(self) -> None:
        self._shutdown_thumbnail_loader()
        Adw.Application.do_shutdown(self)


def main() -> int:
    import sys

    app = WallflowApp()
    return app.run(sys.argv)
