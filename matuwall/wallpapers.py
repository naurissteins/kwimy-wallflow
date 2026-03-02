from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def list_wallpapers(directory: Path) -> list[Path]:
    if not directory.exists():
        return []

    results: list[Path] = []
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_EXTS:
            continue
        results.append(entry)

    results.sort(key=lambda p: p.name.lower())
    return results
