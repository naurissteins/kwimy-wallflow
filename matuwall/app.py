from __future__ import annotations

import argparse
import os
import signal
import socket
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
from .paths import (
    APP_ID,
    ASSETS_DIR,
    CACHE_DIR,
    IPC_SOCKET_PATH,
    PID_FILE_PATH,
    RUNTIME_DIR,
    UI_PID_FILE_PATH,
    USER_CSS_PATH,
)
from .ui.navigation import NavigationMixin
from .ui.thumbnails import ThumbnailMixin
from .wallpapers import list_wallpapers


class MatuwallApp(Adw.Application, NavigationMixin, ThumbnailMixin):
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
        self._panel_margins: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._backdrop_enabled = False
        self._backdrop_opacity = 0.0
        self._backdrop_click_to_close = True
        self._keep_ui_alive = False
        self._needs_reload = False
        self._daemon_enabled = False
        self._daemon_start_hidden = False
        self._pending_action: str | None = None
        self._quit_requested = False
        self._ipc_socket: socket.socket | None = None
        self._ipc_watch_id: int | None = None
        self._backdrop_window: Gtk.Window | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        if LAYER_SHELL_ERROR:
            self._log(f"gtk4-layer-shell import error: {LAYER_SHELL_ERROR}")
        if os.environ.get("MATUWALL_UI") == "1":
            self._setup_ui_signal_handlers()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = list(command_line.get_arguments())
        opts = self._parse_args([str(a) for a in args[1:]])

        if opts.daemon:
            self._daemon_enabled = True
            self._daemon_start_hidden = True
            self.hold()
            self._setup_ipc()
            self._setup_signal_handlers()

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
                self._hide_window()
            else:
                self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "show":
            self._show_window()
            self._pending_action = None
            return
        if self._pending_action == "hide":
            self._hide_window()
            self._pending_action = None
            return

        if self._daemon_start_hidden:
            self._daemon_start_hidden = False
            return

        self._show_window()

    def _show_window(self) -> None:
        if not self._window:
            return
        if self._window.get_visible():
            return
        if self._needs_reload:
            self._reload_content()
        if self._panel_mode and self._backdrop_enabled:
            self._show_backdrop()
        self._window.present()
        if self._flowbox:
            self._flowbox.grab_focus()
        if self._panel_mode:
            GLib.idle_add(self._refresh_layer_shell)

    def _show_backdrop(self) -> None:
        if not self._backdrop_window:
            return
        if self._backdrop_window.get_visible():
            return
        self._backdrop_window.present()

    def _refresh_layer_shell(self) -> bool:
        if not self._panel_mode or not self._window:
            return False
        self._apply_layer_shell(
            self._window,
            self._panel_edge,
            self._panel_size,
            self._panel_fit,
            self._panel_margins,
        )
        return False

    def _setup_ipc(self) -> None:
        if self._ipc_socket is not None:
            return
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        try:
            if IPC_SOCKET_PATH.exists():
                IPC_SOCKET_PATH.unlink()
        except OSError:
            pass
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(IPC_SOCKET_PATH))
            sock.listen(5)
            sock.setblocking(False)
        except OSError:
            return
        self._ipc_socket = sock
        try:
            self._ipc_watch_id = GLib.io_add_watch(
                sock.fileno(), GLib.IO_IN, self._on_ipc_ready
            )
        except Exception:
            self._ipc_watch_id = None
        self._write_pid_file()

    def _write_pid_file(self) -> None:
        try:
            PID_FILE_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
        except OSError:
            return

    def _setup_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGUSR1, self._on_sig_show)
            signal.signal(signal.SIGUSR2, self._on_sig_hide)
            signal.signal(signal.SIGHUP, self._on_sig_toggle)
        except Exception:
            return

    def _setup_ui_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGUSR1, self._on_sig_show)
            signal.signal(signal.SIGUSR2, self._on_sig_hide)
            signal.signal(signal.SIGHUP, self._on_sig_toggle)
        except Exception:
            return

    def _on_sig_show(self, _signum, _frame) -> None:
        GLib.idle_add(self._show_window)

    def _on_sig_hide(self, _signum, _frame) -> None:
        GLib.idle_add(self._hide_window)

    def _on_sig_toggle(self, _signum, _frame) -> None:
        GLib.idle_add(self._toggle_window)

    def _on_ipc_ready(self, _source, _condition) -> bool:
        if not self._ipc_socket:
            return False
        while True:
            try:
                conn, _addr = self._ipc_socket.accept()
            except BlockingIOError:
                break
            except OSError:
                return True
            try:
                data = conn.recv(1024)
            except OSError:
                data = b""
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            command = data.decode("utf-8", "ignore").strip().lower()
            if command == "show":
                self._show_window()
            elif command == "hide":
                self._hide_window()
            elif command == "toggle":
                self._toggle_window()
            elif command == "quit":
                self.quit()
        return True

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
        panel_margins = (
            max(0, int(self.config.panel_margin_top)),
            max(0, int(self.config.panel_margin_bottom)),
            max(0, int(self.config.panel_margin_left)),
            max(0, int(self.config.panel_margin_right)),
        )
        self._panel_edge = panel_edge
        self._panel_size = panel_size
        self._panel_fit = panel_fit
        self._panel_margins = panel_margins
        self._backdrop_enabled = bool(self.config.backdrop_enabled)
        self._backdrop_opacity = max(
            0.0, min(1.0, float(self.config.backdrop_opacity))
        )
        self._backdrop_click_to_close = bool(self.config.backdrop_click_to_close)
        self._keep_ui_alive = bool(self.config.keep_ui_alive)
        if (
            self._backdrop_enabled
            and self._backdrop_click_to_close
            and self._backdrop_opacity <= 0.0
        ):
            # Keep a tiny alpha so the compositor still delivers input.
            self._backdrop_opacity = 0.01
        if self._panel_mode:
            monitor_width, monitor_height = self._get_primary_monitor_size()
            target_width, target_height = self._panel_target_size(
                panel_edge,
                panel_size,
                panel_fit,
                monitor_width,
                monitor_height,
                panel_margins,
            )
            window.set_default_size(target_width, target_height)
            window.set_decorated(False)
            window.set_resizable(False)
        else:
            window.set_default_size(
                int(self.config.window_width), int(self.config.window_height)
            )
        window.set_title("Matuwall")
        if not self._panel_mode:
            window.set_decorated(bool(self.config.window_decorations))
        window.connect("close-request", self._on_close_request)
        self._window = window
        if self.config.panel_mode and LayerShell is None:
            self._log("gtk4-layer-shell not available; panel_mode disabled")
        if self._panel_mode and self._backdrop_enabled:
            self._ensure_backdrop_window()
        if self._panel_mode:
            self._apply_layer_shell(
                window, panel_edge, panel_size, panel_fit, panel_margins
            )
        if self._panel_mode:
            self._log(
                "panel_mode=%s edge=%s size=%s fit=%s margins=%s backend=%s target=%sx%s"
                % (
                    self._panel_mode,
                    panel_edge,
                    panel_size,
                    panel_fit,
                    panel_margins,
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

        self._build_content()

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self._daemon_enabled:
            self._hide_window()
            return True
        if self._keep_ui_alive and os.environ.get("MATUWALL_UI") == "1":
            self._hide_window()
            return True
        if self._backdrop_enabled:
            self._hide_window()
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
        self,
        window: Gtk.Window,
        panel_edge: str,
        panel_size: int,
        fit_to_screen: bool,
        panel_margins: tuple[int, int, int, int],
    ) -> None:
        if LayerShell is None:
            return
        LayerShell.init_for_window(window)
        try:
            LayerShell.set_namespace(window, "matuwall")
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
        margin_top, margin_bottom, margin_left, margin_right = panel_margins
        LayerShell.set_margin(window, LayerShell.Edge.TOP, margin_top)
        LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, margin_bottom)
        LayerShell.set_margin(window, LayerShell.Edge.LEFT, margin_left)
        LayerShell.set_margin(window, LayerShell.Edge.RIGHT, margin_right)

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
            panel_margins,
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

    def _ensure_backdrop_window(self) -> None:
        if self._backdrop_window:
            return
        backdrop = Adw.ApplicationWindow(application=self)
        backdrop.set_title("Matuwall Backdrop")
        backdrop.set_decorated(False)
        backdrop.set_resizable(False)
        backdrop.set_opacity(self._backdrop_opacity)
        backdrop.add_css_class("matuwall-backdrop")
        box = Gtk.Box()
        box.set_hexpand(True)
        box.set_vexpand(True)
        box.set_can_target(True)
        backdrop.set_content(box)
        if self._backdrop_click_to_close:
            click = Gtk.GestureClick()
            click.connect("pressed", self._on_backdrop_pressed)
            box.add_controller(click)
        self._backdrop_window = backdrop
        self._apply_backdrop_layer_shell(backdrop)

    def _apply_backdrop_layer_shell(self, window: Gtk.Window) -> None:
        if LayerShell is None:
            return
        LayerShell.init_for_window(window)
        try:
            LayerShell.set_namespace(window, "matuwall-backdrop")
        except Exception:
            pass
        LayerShell.set_layer(window, LayerShell.Layer.TOP)
        LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(window, -1)
        LayerShell.set_anchor(window, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(window, LayerShell.Edge.RIGHT, True)
        LayerShell.set_anchor(window, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
        monitor_width, monitor_height = self._get_primary_monitor_size()
        if monitor_width and monitor_height:
            self._set_layer_size(window, monitor_width, monitor_height)
        self._apply_panel_size_hint(window, monitor_width, monitor_height)

    def _on_backdrop_pressed(self, *_args) -> None:
        self._hide_window()

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
        panel_margins: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        margin_top, margin_bottom, margin_left, margin_right = panel_margins
        if panel_edge in {"left", "right"}:
            width = panel_size
            height = (
                monitor_height - margin_top - margin_bottom
                if fit_to_screen and monitor_height
                else 1
            )
        else:
            width = (
                monitor_width - margin_left - margin_right
                if fit_to_screen and monitor_width
                else 1
            )
            height = panel_size
        return int(max(1, width)), int(max(1, height))

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
        css_path = USER_CSS_PATH if USER_CSS_PATH.exists() else ASSETS_DIR / "style.css"
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
        if self._load_index < len(self._wallpaper_paths):
            GLib.idle_add(self._load_next_batch)
        return False

    def _reload_content(self) -> None:
        self._needs_reload = False
        if not self.config:
            return
        self._init_thumbnail_loader()
        if not self._wallpaper_paths:
            wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
            if not wallpaper_dir.exists():
                if self._scroller:
                    self._scroller.set_child(
                    self._build_empty_state(
                        "Wallpaper folder not found",
                        f"{wallpaper_dir}\nSet a valid path in ~/.config/matuwall/config.json",
                    )
                )
                self._flowbox = None
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
                self._flowbox = None
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
        self._scroller = scroller

        if not self.config.mouse_enabled:
            scroller.set_can_target(False)
        scroller.set_margin_top(max(0, int(self.config.content_inset_top)))
        scroller.set_margin_bottom(max(0, int(self.config.content_inset_bottom)))
        scroller.set_margin_start(max(0, int(self.config.content_inset_left)))
        scroller.set_margin_end(max(0, int(self.config.content_inset_right)))

        toast_overlay = Adw.ToastOverlay()
        toast_overlay.set_child(scroller)
        self._toast_overlay = toast_overlay

        toolbar_view.set_content(toast_overlay)
        self._window.set_content(toolbar_view)

        wallpaper_dir = Path(self.config.wallpaper_dir).expanduser()
        if not wallpaper_dir.exists():
            self._flowbox = None
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
            self._flowbox = None
            scroller.set_child(
                self._build_empty_state(
                    "No wallpapers found",
                    f"Add images to {wallpaper_dir}\nSupported: jpg, jpeg, png, webp, bmp, gif",
                )
            )
            return
        self._log(
            f"wallpapers found: {len(self._wallpaper_paths)} in {wallpaper_dir}"
        )

        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_activate_on_single_click(True)
        if self._scroll_direction == "horizontal":
            flowbox.set_orientation(Gtk.Orientation.VERTICAL)
        else:
            flowbox.set_orientation(Gtk.Orientation.HORIZONTAL)
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_halign(Gtk.Align.START)
        flowbox.set_max_children_per_line(6)
        flowbox.set_column_spacing(12)
        flowbox.set_row_spacing(12)
        flowbox.add_css_class("matuwall-grid")
        if (
            self._panel_mode
            and self._scroll_direction == "vertical"
            and self._panel_edge in {"left", "right"}
        ):
            flowbox.set_max_children_per_line(1)
            flowbox.set_min_children_per_line(1)
            flowbox.set_homogeneous(True)
            flowbox.set_halign(Gtk.Align.FILL)
            flowbox.set_hexpand(True)
        self._attach_navigation(flowbox)
        self._flowbox = flowbox
        viewport_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL
            if self._scroll_direction != "horizontal"
            else Gtk.Orientation.HORIZONTAL
        )
        viewport_box.set_valign(Gtk.Align.START)
        viewport_box.set_halign(Gtk.Align.START)
        viewport_box.set_hexpand(True)
        viewport_box.set_vexpand(True)
        viewport_box.add_css_class("matuwall-viewport")
        viewport_box.append(flowbox)
        scroller.set_child(viewport_box)

        if not self.config.mouse_enabled:
            flowbox.set_activate_on_single_click(False)
            flowbox.set_can_target(False)

        self._init_thumbnail_loader()
        self._load_index = 0
        GLib.idle_add(self._load_next_batch)

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

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)

    def do_shutdown(self) -> None:
        self._shutdown_thumbnail_loader()
        if self._daemon_enabled:
            if self._ipc_watch_id is not None:
                try:
                    GLib.source_remove(self._ipc_watch_id)
                except Exception:
                    pass
                self._ipc_watch_id = None
            if self._ipc_socket is not None:
                try:
                    self._ipc_socket.close()
                except Exception:
                    pass
                self._ipc_socket = None
            try:
                if IPC_SOCKET_PATH.exists():
                    IPC_SOCKET_PATH.unlink()
            except OSError:
                pass
            try:
                if PID_FILE_PATH.exists():
                    PID_FILE_PATH.unlink()
            except OSError:
                pass
        if os.environ.get("MATUWALL_UI") == "1":
            try:
                if UI_PID_FILE_PATH.exists():
                    UI_PID_FILE_PATH.unlink()
            except OSError:
                pass
        Adw.Application.do_shutdown(self)


def main() -> int:
    import sys

    app = MatuwallApp()
    return app.run(sys.argv)
