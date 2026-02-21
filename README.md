# Kwimy Wallflow

A minimal GTK4 + libadwaita wallpaper picker that runs `matugen` on click and applies colors from the selected wallpaper.

## Features
- Lazy-loads wallpapers from a configured folder
- Runs `matugen image <wallpaper> -m <mode>` on click
- Thumbnail caching in `~/.cache/kwimy-wallflow/`
- Configs `~/.config/kwimy-wallflow/config.json`
- CSS theming `assets/style.css`

## Install Dependencies
```
sudo pacman -S python python-gobject gtk4 libadwaita
```

## Run (from repo)
```
python -m kwimy_wallflow
```

## Configuration
Config file path:
- `~/.config/kwimy-wallflow/config.json`

Default config:
```json
{
  "wallpaper_dir": "~/Pictures/Wallpapers",
  "matugen_mode": "dark",
  "thumbnail_size": 256,
  "batch_size": 16,
  "window_decorations": false
}
```

## Styling
Edit `assets/style.css` to change background, borders, and typography.

## Notes
- `matugen` must be available in `PATH`.
- The app reads wallpapers from `wallpaper_dir` and supports: `jpg`, `jpeg`, `png`, `webp`, `bmp`, `gif`.
