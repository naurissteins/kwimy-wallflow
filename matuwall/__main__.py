from __future__ import annotations

import logging
import sys

from .cli import format_status, parse_cli_command, send_ipc_command


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
        from .daemon import run_daemon

        return run_daemon()

    if "--ui" in argv:
        from .app import main as app_main

        return app_main()

    command = parse_cli_command(argv)
    if command == "status":
        print(format_status())
        return 0
    if command and send_ipc_command(command):
        return 0
    if command in {"hide", "quit", "reload"}:
        print("matuwall daemon is not running", file=sys.stderr)
        return 1

    from .app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
