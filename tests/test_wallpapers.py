from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from matuwall.wallpapers import list_wallpapers


class WallpaperTests(unittest.TestCase):
    def test_lists_supported_files_sorted_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "b.PNG").write_text("x", encoding="utf-8")
            (directory / "A.jpg").write_text("x", encoding="utf-8")
            (directory / "note.txt").write_text("x", encoding="utf-8")
            (directory / "subdir").mkdir()

            files = list_wallpapers(directory)
            names = [f.name for f in files]
            self.assertEqual(names, ["A.jpg", "b.PNG"])

    def test_missing_directory_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "missing"
            self.assertEqual(list_wallpapers(directory), [])


if __name__ == "__main__":
    unittest.main()
