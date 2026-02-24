from __future__ import annotations
from pathlib import Path
from gi.repository import GObject

class WallpaperItem(GObject.Object):
    path_str = GObject.Property(type=str)
    
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.path_str = str(path)
        self.name = path.name
