# Matuwall

A minimal GTK4 + libadwaita wallpaper picker for Wayland. Select a wallpaper and Matuwall triggers [matugen](https://github.com/InioX/matugen) to generate and apply colors from the chosen image.

NOTE: Matuwall does not manage matugen configuration, users are expected to have their own matugen setup in place.

## Features
- Two UI layouts: centered window mode and edge panel mode (`left`, `right`, `top`, `bottom`)
- Daemon-first workflow with IPC controls (`--show`, `--hide`, `--toggle`, `--quit`)
- Responsive startup with lazy, batched wallpaper loading
- Background thumbnail generation with persistent cache in `~/.cache/matuwall/`
- One-action apply flow: activate a thumbnail to run `matugen image <wallpaper> -m <mode>`
- Keyboard navigation (`Enter` apply, `Esc` close), plus optional mouse interaction
- Panel auto-fit behavior: oversized `panel_thumbs_col` values are capped to available monitor space
- User theming through `~/.config/matuwall/style.css`

> [!TIP]  
> If `"keep_ui_alive": true`, changes to `config.json`, `~/.config/matuwall/style.css`, or your wallpaper folder won’t take effect until you restart the `matuwall` service `(systemctl --user restart matuwall.service)`

## Install Dependencies
```
sudo pacman -S python python-gobject gtk4 libadwaita gtk-layer-shell
```

## Run (from repo)
```
python -m matuwall
```

## Daemon Mode
Start daemon mode once:
```
matuwall --daemon
```

Control it from any terminal:
```
matuwall --toggle
matuwall --show
matuwall --hide
matuwall --quit
```

Behavior:
- `--show` / `--hide` / `--toggle` / `--quit` use IPC and do not create duplicate windows
- The daemon itself runs without GTK and starts a UI process only when needed
- If `keep_ui_alive` is `false`, the UI process exits on hide (lower idle memory)
- `config.json` is watched and reloaded by the daemon in ~0.5s; UI-only changes apply on next UI start when `keep_ui_alive` is `true`

## Panel Mode (Layer Shell)
Use panel mode to anchor Matuwall to a Wayland screen edge:
```
"panel_mode": true,
"panel_edge": "left",
"panel_thumbs_col": 3,
"panel_margin_top": 30
```
`panel_thumbs_col` is treated as a requested visible count and auto-capped to monitor space, so the panel always stays fully on-screen.

## Autostart (systemd --user)
```
mkdir -p ~/.config/systemd/user
cp systemd/matuwall.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now matuwall.service

systemctl --user daemon-reload
systemctl --user restart matuwall.service
```

If you installed via a local venv, update `ExecStart` in the service file to point at your venv binary.
If you are on Wayland, the service sets `GDK_BACKEND=wayland` to ensure layer-shell works.
If your compositor uses a different `WAYLAND_DISPLAY`, update it in `systemd/matuwall.service`.
If you see “Failed to initialize layer surface”, set `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so`.
If `--toggle` opens a new normal window, make sure the service has `DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus`.
You can check the service environment with `systemctl --user show matuwall.service -p Environment`.

## Configuration
Config file path:
- `~/.config/matuwall/config.json`

Default config:
```json
{
  "wallpaper_dir": "~/Pictures/Wallpapers",
  "matugen_mode": "dark",
  "thumbnail_size": 256,
  "thumbnail_shape": "landscape",
  "batch_size": 16,
  "window_decorations": false,
  "window_grid_cols": 3,
  "window_grid_rows": 3,
  "window_grid_max_width_pct": 80,
  "mouse_enabled": true,
  "keep_ui_alive": false,
  "panel_mode": false,
  "panel_edge": "left",
  "panel_thumbs_col": 3,
  "panel_exclusive_zone": -1,
  "panel_margin_top": 0,
  "panel_margin_bottom": 0,
  "panel_margin_left": 0,
  "panel_margin_right": 0
}
```

## Hyprland
```
windowrule = float true, match:class com\.kwimy\.Matuwall
windowrule = animation slide top, match:class com\.kwimy\.Matuwall
windowrule = rounding 15, match:class com\.kwimy\.Matuwall
windowrule = border_size 0, match:class com\.kwimy\.Matuwall
windowrule = rounding_power 2, match:class com\.kwimy\.Matuwall
windowrule = no_shadow on, match:class com\.kwimy\.Matuwall

layerrule = match:namespace matuwall, blur on
layerrule = match:namespace matuwall, ignore_alpha 0.5
```

## Styling
Edit `~/.config/matuwall/style.css` to change background, borders, and typography. 
If you want to refresh it, delete the file and restart the app and it will be regenerated from the default template.

## Notes
- `matugen` must be available in `PATH`.
- Wallpapers are read from `wallpaper_dir` and support: `jpg`, `jpeg`, `png`, `webp`, `bmp`, `gif`.
- `thumbnail_size` defines thumbnail width and is capped to `1000` to avoid oversized thumbnails.
- `thumbnail_shape` controls aspect ratio: `landscape` (16:9, default) or `square` (1:1).
- `batch_size` controls how many thumbnails are appended per UI idle cycle (smaller = smoother, larger = faster fill). Clamped to `1..128`.
- `window_grid_cols` / `window_grid_rows` control the default window size based on thumbnail dimensions. Each is clamped to `1..12`.
- `window_grid_max_width_pct` caps the window width as a percentage of the screen (default 80).
- `mouse_enabled` toggles pointer interaction (click, hover, scroll).
- `keep_ui_alive` keeps the UI process running between show/hide (faster open, higher memory use).
- `panel_mode` enables layer-shell mode (requires `gtk-layer-shell` with Gtk4 typelibs).
- `panel_edge` can be `left`, `right`, `top`, `bottom`.
- `panel_thumbs_col` is the number of thumbnails to display (width for top/bottom panels, height for left/right). If it's too large for your monitor/margins, Matuwall automatically caps visible thumbs to fit on screen.
- `panel_exclusive_zone` controls reserved space (`-1` = none). Clamped to `-1..4096`.
- `panel_margin_top` / `panel_margin_bottom` add margins in pixels (useful to sit under a top bar).
- `panel_margin_left` / `panel_margin_right` add margins for top/bottom panels.
