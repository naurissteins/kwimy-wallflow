from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matuwall.config as config


class ConfigTests(unittest.TestCase):
    def test_strip_json_comments(self) -> None:
        raw = """// header\n# second\n{\n  \"foo\": 1\n}\n"""
        stripped = config._strip_json_comments(raw)
        self.assertEqual(stripped, "{\n  \"foo\": 1\n}")

    def test_load_config_supports_commented_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            assets_dir = root / "assets"
            cfg_dir.mkdir()
            assets_dir.mkdir()
            (assets_dir / "style.css").write_text("window {}\n", encoding="utf-8")

            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(
                """
# comment line
{
  // inline comment line
  "panel_thumbs_col": 7,
  "window_grid_cols": 4
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ), patch.object(config, "ASSETS_DIR", assets_dir):
                loaded = config.load_config()

            self.assertEqual(loaded.panel_thumbs_col, 7)
            self.assertEqual(loaded.window_grid_cols, 4)

    def test_write_config_persists_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            assets_dir = root / "assets"
            cfg_dir.mkdir()
            assets_dir.mkdir()
            (assets_dir / "style.css").write_text("window {}\n", encoding="utf-8")
            cfg_path = cfg_dir / "config.json"

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ), patch.object(config, "ASSETS_DIR", assets_dir):
                config.write_config(config.DEFAULT_CONFIG)

            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertIn("panel_thumbs_col", payload)
            self.assertNotIn("panel_fit", payload)
            self.assertNotIn("show_scrollbar", payload)
            self.assertNotIn("backdrop_enabled", payload)


if __name__ == "__main__":
    unittest.main()
