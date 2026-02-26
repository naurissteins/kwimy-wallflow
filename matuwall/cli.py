from __future__ import annotations

import argparse
import os
import signal
import socket
from pathlib import Path

from .paths import IPC_SOCKET_PATH, PID_FILE_PATH, RUNTIME_DIR, UI_PID_FILE_PATH


def parse_cli_command(argv: list[str]) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--ui", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--hide", action="store_true")
    parser.add_argument("--toggle", action="store_true")
    parser.add_argument("--quit", action="store_true")
    opts, _ = parser.parse_known_args(argv)
    if opts.daemon or opts.ui:
        return None
    if opts.show:
        return "show"
    if opts.hide:
        return "hide"
    if opts.toggle:
        return "toggle"
    if opts.quit:
        return "quit"
    if opts.reload:
        return "reload"
    if opts.status:
        return "status"
    return None


def send_ipc_command(command: str) -> bool:
    if _send_ipc_socket(command):
        return True
    return _send_ipc_signal(command)


def _send_ipc_socket(command: str) -> bool:
    candidates: list[Path] = [IPC_SOCKET_PATH]
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    candidates.append(Path(runtime_dir) / "matuwall" / "ipc.sock")

    for socket_path in candidates:
        if not socket_path.exists():
            continue
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(socket_path))
            sock.send(command.encode("utf-8"))
            sock.close()
            return True
        except OSError:
            continue
    return False


def _send_ipc_signal(command: str) -> bool:
    if not PID_FILE_PATH.exists():
        return False
    try:
        raw = PID_FILE_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    sig_map = {
        "show": signal.SIGUSR1,
        "hide": signal.SIGUSR2,
        "toggle": signal.SIGHUP,
        "quit": signal.SIGTERM,
    }
    sig = sig_map.get(command)
    if not sig:
        return False
    try:
        os.kill(pid, sig)
        return True
    except OSError:
        return False


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _socket_reachable(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(path))
        sock.close()
        return True
    except OSError:
        return False


def format_status() -> str:
    daemon_pid = _read_pid(PID_FILE_PATH)
    daemon_running = bool(daemon_pid and _pid_exists(daemon_pid))

    ui_pid = _read_pid(UI_PID_FILE_PATH)
    ui_running = bool(ui_pid and _pid_exists(ui_pid))

    socket_exists = IPC_SOCKET_PATH.exists()
    socket_ready = _socket_reachable(IPC_SOCKET_PATH)

    daemon_state = "running" if daemon_running else "stopped"
    ui_state = "running" if ui_running else "stopped"
    if socket_ready:
        socket_state = "ready"
    elif socket_exists and daemon_running:
        socket_state = "present"
    elif socket_exists:
        socket_state = "stale"
    else:
        socket_state = "missing"

    daemon_pid_text = str(daemon_pid) if daemon_running and daemon_pid else "n/a"
    ui_pid_text = str(ui_pid) if ui_running and ui_pid else "n/a"

    lines = [
        f"Runtime Dir: {RUNTIME_DIR}",
        f"IPC Socket: {IPC_SOCKET_PATH} ({socket_state})",
        f"Daemon: {daemon_state} (pid: {daemon_pid_text})",
        f"UI: {ui_state} (pid: {ui_pid_text})",
    ]
    return "\n".join(lines)
