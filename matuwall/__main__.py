from __future__ import annotations

import sys

from .cli import parse_cli_command, send_ipc_command


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--daemon" in argv:
        from .daemon import run_daemon

        return run_daemon()

    if "--ui" in argv:
        from .app import main as app_main

        return app_main()

    command = parse_cli_command(argv)
    if command and send_ipc_command(command):
        return 0

    from .app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
