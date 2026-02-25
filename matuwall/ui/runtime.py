from __future__ import annotations

import os
import signal
import socket

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gio, GLib

from ..paths import IPC_SOCKET_PATH, PID_FILE_PATH, RUNTIME_DIR


class RuntimeMixin:
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
