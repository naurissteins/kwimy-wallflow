from __future__ import annotations

import logging
import os
import selectors
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from .config import CONFIG_PATH, load_config
from .paths import IPC_SOCKET_PATH, PID_FILE_PATH, RUNTIME_DIR, UI_PID_FILE_PATH

LOGGER = logging.getLogger("matuwall.daemon")


class MatuwallDaemon:
    def __init__(self) -> None:
        self._selector = selectors.DefaultSelector()
        self._socket: socket.socket | None = None
        self._running = True
        self._keep_ui_alive = False
        self._panel_mode_requested = False
        self._config_mtime_ns: int | None = None
        self._config_size: int | None = None
        self._startup_error: str | None = None
        self._load_config(force=True)

    def run(self) -> int:
        self._setup_socket()
        if not self._socket:
            if self._startup_error:
                LOGGER.error(self._startup_error)
            else:
                LOGGER.error("Failed to start daemon")
            return 1
        self._write_pid_file()
        LOGGER.info("Daemon started (ipc=%s)", IPC_SOCKET_PATH)
        try:
            while self._running:
                self._load_config()
                for key, _mask in self._selector.select(timeout=0.5):
                    callback = key.data
                    callback(key.fileobj)
        finally:
            self._cleanup()
            LOGGER.info("Daemon stopped")
        return 0

    def _setup_socket(self) -> None:
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._startup_error = (
                f"Failed to create runtime directory {RUNTIME_DIR}: {exc}"
            )
            return
        try:
            if IPC_SOCKET_PATH.exists():
                IPC_SOCKET_PATH.unlink()
        except OSError as exc:
            self._startup_error = (
                f"Failed to remove stale socket {IPC_SOCKET_PATH}: {exc}"
            )
            pass
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(IPC_SOCKET_PATH))
            sock.listen(8)
            sock.setblocking(False)
        except OSError as exc:
            self._startup_error = (
                f"Failed to bind IPC socket {IPC_SOCKET_PATH}: {exc}"
            )
            return
        self._socket = sock
        self._selector.register(sock, selectors.EVENT_READ, self._accept)

    def _accept(self, sock: socket.socket) -> None:
        try:
            conn, _addr = sock.accept()
        except OSError:
            return
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
        self._handle_command(command)

    def _handle_command(self, command: str) -> None:
        if command == "show":
            self._show_ui()
        elif command == "hide":
            self._hide_ui()
        elif command == "toggle":
            if self._keep_ui_alive and self._ui_running():
                self._signal_ui(signal.SIGHUP)
            elif self._ui_running():
                self._hide_ui()
            else:
                self._show_ui()
        elif command == "quit":
            self._hide_ui()
            self._running = False
        elif command == "reload":
            self._reload()

    def _show_ui(self) -> None:
        if self._ui_running():
            if self._keep_ui_alive:
                self._signal_ui(signal.SIGUSR1)
            return
        env = self._prepare_ui_env()
        env["MATUWALL_UI"] = "1"
        log_path: Path | None = RUNTIME_DIR / "ui.log"
        try:
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_path = None
        if log_path:
            with log_path.open("ab") as log:
                log.write(b"\n--- matuwall ui start ---\n")
                log.flush()
                proc = subprocess.Popen(
                    [sys.executable, "-m", "matuwall", "--ui"],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
        else:
            proc = subprocess.Popen(
                [sys.executable, "-m", "matuwall", "--ui"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self._write_ui_pid(proc.pid)

    def _prepare_ui_env(self) -> dict[str, str]:
        env = os.environ.copy()
        runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        env.setdefault("XDG_RUNTIME_DIR", runtime_dir)

        runtime_path = Path(runtime_dir)
        wayland_display = env.get("WAYLAND_DISPLAY")
        if not wayland_display:
            candidates = sorted(runtime_path.glob("wayland-*"))
            if candidates:
                wayland_display = candidates[0].name
                env["WAYLAND_DISPLAY"] = wayland_display
        if wayland_display:
            env.setdefault("XDG_SESSION_TYPE", "wayland")
            current_backend = env.get("GDK_BACKEND", "").strip()
            if not current_backend:
                env["GDK_BACKEND"] = "wayland"
            elif "wayland" not in {
                item.strip() for item in current_backend.split(",") if item.strip()
            }:
                env["GDK_BACKEND"] = f"wayland,{current_backend}"
        else:
            LOGGER.warning(
                "WAYLAND_DISPLAY is not set; panel mode may run without layer-shell"
            )

        if not env.get("DBUS_SESSION_BUS_ADDRESS"):
            bus_path = runtime_path / "bus"
            if bus_path.exists():
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"

        if self._panel_mode_requested:
            preload_candidates = (
                Path("/usr/lib/libgtk4-layer-shell.so"),
                Path("/usr/lib64/libgtk4-layer-shell.so"),
            )
            for lib_path in preload_candidates:
                if not lib_path.exists():
                    continue
                current_preload = env.get("LD_PRELOAD", "")
                if str(lib_path) in current_preload:
                    break
                if current_preload:
                    env["LD_PRELOAD"] = f"{current_preload}:{lib_path}"
                else:
                    env["LD_PRELOAD"] = str(lib_path)
                break
        return env

    def _hide_ui(self) -> None:
        pid = self._read_ui_pid()
        if not pid:
            return
        if not self._pid_exists(pid):
            self._clear_ui_pid()
            return
        if self._keep_ui_alive:
            self._signal_ui(signal.SIGUSR2)
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            self._clear_ui_pid()
            return
        self._wait_for_exit(pid, timeout=1.0)
        if self._pid_exists(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        self._clear_ui_pid()

    def _reload(self) -> None:
        ui_was_running = self._ui_running()
        self._load_config(force=True)
        if not ui_was_running:
            LOGGER.info("Reloaded daemon config")
            return
        keep_ui_alive = self._keep_ui_alive
        self._keep_ui_alive = False
        try:
            self._hide_ui()
        finally:
            self._keep_ui_alive = keep_ui_alive
        self._show_ui()
        LOGGER.info("Reloaded daemon config and restarted UI")

    def _wait_for_exit(self, pid: int, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._pid_exists(pid):
                return
            time.sleep(0.05)

    def _ui_running(self) -> bool:
        pid = self._read_ui_pid()
        if not pid:
            return False
        if self._pid_exists(pid):
            if self._pid_is_ui(pid):
                return True
        self._clear_ui_pid()
        return False

    def _signal_ui(self, sig: signal.Signals) -> None:
        pid = self._read_ui_pid()
        if not pid:
            return
        if not self._pid_exists(pid):
            self._clear_ui_pid()
            return
        try:
            os.kill(pid, sig)
        except OSError:
            self._clear_ui_pid()

    @staticmethod
    def _pid_is_ui(pid: int) -> bool:
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        try:
            data = cmdline_path.read_bytes()
        except OSError:
            return False
        if b"matuwall" not in data:
            return False
        if b"--ui" not in data:
            return False
        return True

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    @staticmethod
    def _write_pid_file() -> None:
        try:
            PID_FILE_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
        except OSError:
            return

    @staticmethod
    def _write_ui_pid(pid: int) -> None:
        try:
            UI_PID_FILE_PATH.write_text(f"{pid}\n", encoding="utf-8")
        except OSError:
            return

    @staticmethod
    def _read_ui_pid() -> int | None:
        try:
            raw = UI_PID_FILE_PATH.read_text(encoding="utf-8").strip()
            return int(raw)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _clear_ui_pid() -> None:
        try:
            if UI_PID_FILE_PATH.exists():
                UI_PID_FILE_PATH.unlink()
        except OSError:
            pass

    def _cleanup(self) -> None:
        self._selector.close()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
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
        self._clear_ui_pid()

    def _load_config(self, force: bool = False) -> None:
        try:
            stat = CONFIG_PATH.stat()
            mtime_ns = stat.st_mtime_ns
            size = stat.st_size
        except OSError:
            mtime_ns = 0
            size = 0
        if (
            not force
            and self._config_mtime_ns == mtime_ns
            and self._config_size == size
        ):
            return
        self._config_mtime_ns = mtime_ns
        self._config_size = size
        cfg = load_config()
        self._keep_ui_alive = bool(cfg.keep_ui_alive)
        self._panel_mode_requested = bool(cfg.panel_mode)


def run_daemon() -> int:
    return MatuwallDaemon().run()
