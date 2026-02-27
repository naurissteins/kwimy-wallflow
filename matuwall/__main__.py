from __future__ import annotations

import logging
import sys

try:
    from .cli import format_status, parse_cli_command, send_ipc_command
    from .config import load_config
except ImportError:
    from matuwall.cli import format_status, parse_cli_command, send_ipc_command
    from matuwall.config import load_config


def _import_daemon_runner():
    try:
        from .daemon import run_daemon
    except ImportError:
        from matuwall.daemon import run_daemon
    return run_daemon


def _import_app_main():
    try:
        from .app import main as app_main
    except ImportError:
        from matuwall.app import main as app_main
    return app_main


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    if argv is None:
        argv = sys.argv[1:]

    if "--daemon" in argv:
        return _import_daemon_runner()()

    if "--ui" in argv:
        return _import_app_main()()

    command = parse_cli_command(argv)
    if command == "status":
        print(format_status())
        return 0
    if command and send_ipc_command(command):
        return 0
    if command in {"show", "toggle"} and load_config().panel_mode:
        print(
            "matuwall daemon is not running (panel_mode=true requires daemon/systemd)",
            file=sys.stderr,
        )
        return 1
    if command in {"hide", "quit", "reload"}:
        print("matuwall daemon is not running", file=sys.stderr)
        return 1

    return _import_app_main()()


if __name__ == "__main__":
    raise SystemExit(main())
