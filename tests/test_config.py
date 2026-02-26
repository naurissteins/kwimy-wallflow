from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
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
            cfg_dir.mkdir()

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
            ):
                loaded = config.load_config()

            self.assertEqual(loaded.panel_thumbs_col, 7)
            self.assertEqual(loaded.window_grid_cols, 4)

    def test_load_config_supports_nested_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()

            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "main": {"window_grid_cols": 5},
                        "theme": {"window_radius": 22},
                        "panel": {"panel_thumbs_col": 9},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                loaded = config.load_config()

            self.assertEqual(loaded.window_grid_cols, 5)
            self.assertEqual(loaded.theme_window_radius, 22)
            self.assertEqual(loaded.panel_thumbs_col, 9)

    def test_write_config_persists_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()
            cfg_path = cfg_dir / "config.json"

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                config.write_config(config.DEFAULT_CONFIG)

            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertIn("main", payload)
            self.assertIn("theme", payload)
            self.assertIn("panel", payload)
            self.assertIn("panel_thumbs_col", payload["panel"])
            self.assertIn("window_bg", payload["theme"])
            self.assertIn("window_radius", payload["theme"])
            self.assertNotIn("card_margin", payload)
            self.assertNotIn("panel_fit", payload)
            self.assertNotIn("show_scrollbar", payload)
            self.assertNotIn("backdrop_enabled", payload)

    def test_thumbnail_size_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()

            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(
                "{\"thumbnail_size\": 999999}\n",
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                loaded = config.load_config()

            self.assertEqual(loaded.thumbnail_size, config.MAX_THUMBNAIL_SIZE)

    def test_limits_are_clamped_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()

            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "batch_size": 999999,
                        "window_grid_cols": 99,
                        "window_grid_rows": 0,
                        "panel_exclusive_zone": -999,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                loaded = config.load_config()

            self.assertEqual(loaded.batch_size, config.MAX_BATCH_SIZE)
            self.assertEqual(loaded.window_grid_cols, config.MAX_WINDOW_GRID_COLS)
            self.assertEqual(loaded.window_grid_rows, 1)
            self.assertEqual(loaded.panel_exclusive_zone, config.MIN_PANEL_EXCLUSIVE_ZONE)

    def test_limits_are_clamped_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()
            cfg_path = cfg_dir / "config.json"

            bad_cfg = replace(
                config.DEFAULT_CONFIG,
                batch_size=0,
                window_grid_cols=0,
                window_grid_rows=999,
                panel_exclusive_zone=999999,
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                config.write_config(bad_cfg)

            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["main"]["batch_size"], 1)
            self.assertEqual(payload["main"]["window_grid_cols"], 1)
            self.assertEqual(
                payload["main"]["window_grid_rows"], config.MAX_WINDOW_GRID_ROWS
            )
            self.assertEqual(
                payload["panel"]["panel_exclusive_zone"],
                config.MAX_PANEL_EXCLUSIVE_ZONE,
            )

    def test_theme_values_are_sanitized_and_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()

            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "theme_window_bg": "red; color: blue;",
                        "theme_card_bg": "",
                        "theme_window_radius": 999,
                        "theme_card_radius": -10,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_DIR", cfg_dir), patch.object(
                config, "CONFIG_PATH", cfg_path
            ):
                loaded = config.load_config()

            self.assertEqual(loaded.theme_window_bg, config.DEFAULT_CONFIG.theme_window_bg)
            self.assertEqual(loaded.theme_card_bg, config.DEFAULT_CONFIG.theme_card_bg)
            self.assertEqual(loaded.theme_window_radius, config.MAX_THEME_RADIUS)
            self.assertEqual(loaded.theme_card_radius, 0)


if __name__ == "__main__":
    unittest.main()
