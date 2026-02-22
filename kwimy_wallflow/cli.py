from __future__ import annotations

import argparse
import os
import signal
import socket
from pathlib import Path

from .paths import IPC_SOCKET_PATH, PID_FILE_PATH


def parse_cli_command(argv: list[str]) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--hide", action="store_true")
    parser.add_argument("--toggle", action="store_true")
    parser.add_argument("--quit", action="store_true")
    opts, _ = parser.parse_known_args(argv)
    if opts.show:
        return "show"
    if opts.hide:
        return "hide"
    if opts.toggle:
        return "toggle"
    if opts.quit:
        return "quit"
    return None


def send_ipc_command(command: str) -> bool:
    if _send_ipc_socket(command):
        return True
    return _send_ipc_signal(command)


def _send_ipc_socket(command: str) -> bool:
    candidates: list[Path] = [IPC_SOCKET_PATH]
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    candidates.append(Path(runtime_dir) / "kwimy-wallflow" / "ipc.sock")

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
