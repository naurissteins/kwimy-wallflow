from __future__ import annotations

import unittest

from matuwall.cli import parse_cli_command


class CliTests(unittest.TestCase):
    def test_parse_prefers_show(self) -> None:
        self.assertEqual(parse_cli_command(["--show"]), "show")

    def test_parse_ignores_daemon_and_ui_modes(self) -> None:
        self.assertIsNone(parse_cli_command(["--daemon"]))
        self.assertIsNone(parse_cli_command(["--ui"]))

    def test_parse_returns_none_for_no_action(self) -> None:
        self.assertIsNone(parse_cli_command([]))


if __name__ == "__main__":
    unittest.main()
