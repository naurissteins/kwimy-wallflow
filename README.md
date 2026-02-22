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
sudo pacman -S python python-gobject gtk4 libadwaita gtk-layer-shell
```

## Run (from repo)
```
python -m kwimy_wallflow
```

## Daemon Mode
Keep the app in memory for instant open:
```
kwimy-wallflow --daemon
```

Toggle or control the window from another terminal:
```
kwimy-wallflow --toggle
kwimy-wallflow --show
kwimy-wallflow --hide
kwimy-wallflow --quit
```

If the daemon is running, `--show`/`--hide`/`--toggle`/`--quit` talk to it directly and won’t spawn extra windows.

## Panel Mode (Layer Shell)
Enable a panel-style window (left/right/top/bottom) using `gtk-layer-shell`:
```
"panel_mode": true,
"panel_edge": "left",
"panel_size": 420,
"panel_margin_top": 30
```

## Autostart (systemd --user)
```
mkdir -p ~/.config/systemd/user
cp systemd/kwimy-wallflow.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kwimy-wallflow.service

systemctl --user daemon-reload
systemctl --user restart kwimy-wallflow.service
```

If you installed via a local venv, update `ExecStart` in the service file to point at your venv binary.
If you are on Wayland, the service sets `GDK_BACKEND=wayland` to ensure layer-shell works.
If your compositor uses a different `WAYLAND_DISPLAY`, update it in `systemd/kwimy-wallflow.service`.
If you see “Failed to initialize layer surface”, set `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so`.
If `--toggle` opens a new normal window, make sure the service has `DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus`.
You can check the service environment with `systemctl --user show kwimy-wallflow.service -p Environment`.

## Configuration
Config file path:
- `~/.config/kwimy-wallflow/config.json`

Default config:
```json
{
  "wallpaper_dir": "~/Pictures/Wallpapers",
  "matugen_mode": "dark",
  "thumbnail_size": 256,
  "thumbnail_shape": "landscape",
  "batch_size": 16,
  "window_decorations": false,
  "show_filenames": false,
  "window_width": 900,
  "window_height": 600,
  "scroll_direction": "vertical",
  "mouse_enabled": true,
  "backdrop_enabled": false,
  "backdrop_opacity": 0.0,
  "backdrop_click_to_close": true,
  "content_inset_top": 0,
  "content_inset_bottom": 0,
  "content_inset_left": 0,
  "content_inset_right": 0,
  "panel_mode": false,
  "panel_edge": "left",
  "panel_size": 420,
  "panel_exclusive_zone": -1,
  "panel_fit_to_screen": true,
  "panel_margin_top": 0,
  "panel_margin_bottom": 0,
  "panel_margin_left": 0,
  "panel_margin_right": 0
}
```

## Styling
Edit `assets/style.css` to change background, borders, and typography.

## Notes
- `matugen` must be available in `PATH`.
- The app reads wallpapers from `wallpaper_dir` and supports: `jpg`, `jpeg`, `png`, `webp`, `bmp`, `gif`.
- `thumbnail_size` is the width. Height depends on `thumbnail_shape`:
  - `landscape` (default): 16:9
  - `square`: 1:1
- `scroll_direction` controls whether the grid scrolls vertically or horizontally. Use `vertical` or `horizontal`.
- `mouse_enabled` toggles pointer interaction (click/hover/scroll).
- `backdrop_enabled` shows a full-screen transparent layer behind the panel.
- `backdrop_opacity` controls the backdrop tint (0.0 to 1.0). Note: if click-to-close is enabled, values at 0.0 are clamped to 0.01 so the compositor still delivers input. **(Wayland compositor fully transparent surfaces often don’t receive input events)** I will update when I will find a solution.
- `backdrop_click_to_close` closes the panel when clicking outside it.
- `content_inset_top` / `content_inset_bottom` add fixed padding inside the window while scrolling.
- `content_inset_left` / `content_inset_right` add fixed padding for horizontal inset.
- `panel_mode` enables layer-shell mode (requires `gtk-layer-shell` with Gtk4 typelibs).
- `panel_edge` can be `left`, `right`, `top`, `bottom`.
- `panel_size` is the fixed width/height used for panel mode.
- `panel_exclusive_zone` controls reserved space (`-1` = none).
- `panel_fit_to_screen` stretches the panel to the full screen along the long edge.
- `panel_margin_top` / `panel_margin_bottom` add margins in pixels (useful to sit under a top bar).
- `panel_margin_left` / `panel_margin_right` add margins for top/bottom panels.
