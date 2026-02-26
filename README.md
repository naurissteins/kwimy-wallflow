# Matuwall

A minimal GTK4 + libadwaita wallpaper picker for Wayland compositor. Matuwall triggers [matugen](https://github.com/InioX/matugen) to generate and apply colors from the chosen image.

NOTE: Matuwall does not manage and include [matugen](https://github.com/InioX/matugen) configuration, you have to use your own matugen setup.  

## 🔥 Features
- Two UI layouts: centered window mode and edge panel (layer shell) mode (`left`, `right`, `top`, `bottom`)
- Daemon first workflow with IPC controls (`--show`, `--hide`, `--toggle`, `--reload`, `--quit`, `--status`)
- Background thumbnail generation with persistent cache in `~/.cache/matuwall/`
- One-action apply flow: activate a thumbnail to run `matugen image <wallpaper> -m <mode>`
- Keyboard navigation (`Enter` apply, `Esc` close, `Arrow keys` to navigate between thumbnails), plus optional mouse interaction
- Styling in `config.json` (colors + corner radius), with optional `colors.json` color override, useful for customizing the appearance with your own colorscheme using matugen

> [!TIP]  
> If `"keep_ui_alive": true`, changes to `config.json`, `colors.json`, or your wallpaper folder won’t take effect until you restart the `matuwall` service `systemctl --user restart matuwall.service` or `matuwall --reload`

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
matuwall --reload
matuwall --quit
matuwall --status
```

Behavior:
- `--show` / `--hide` / `--toggle` / `--quit` use IPC and do not create duplicate windows
- `--reload` reloads daemon config and restarts UI if it is currently running
- The daemon itself runs without GTK and starts a UI process only when needed
- If `keep_ui_alive` is `false`, the UI process exits on hide (lower idle memory)
- `config.json` is watched and reloaded by the daemon in ~0.5s; UI-only changes apply on next UI start when `keep_ui_alive` is `true`

## Panel Mode (Layer Shell)
Use panel mode to anchor Matuwall to a Wayland screen edge:
```
"panel": {
  "panel_mode": true,
  "panel_edge": "left",
  "panel_thumbs_col": 3,
  "panel_margin_top": 30
}
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
  "main": {
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
    "keep_ui_alive": false
  },
  "theme": {
    "window_bg": "rgba(15, 18, 22, 0.58)",
    "text_color": "#e7e7e7",
    "header_bg_start": "rgba(20, 25, 34, 0.58)",
    "header_bg_end": "rgba(20, 25, 34, 0.78)",
    "backdrop_bg": "rgba(0, 0, 0, 0.0)",
    "card_bg": "rgba(255, 255, 255, 0.04)",
    "card_border": "rgba(255, 255, 255, 0.05)",
    "card_hover_bg": "rgba(255, 255, 255, 0.08)",
    "card_hover_border": "rgba(255, 255, 255, 0.2)",
    "card_selected_bg": "rgba(255, 255, 255, 0.12)",
    "card_selected_border": "rgba(255, 255, 255, 0.25)",
    "window_radius": 15,
    "card_radius": 14,
    "thumb_radius": 10
  },
  "panel": {
    "panel_mode": false,
    "panel_edge": "left",
    "panel_thumbs_col": 3,
    "panel_exclusive_zone": -1,
    "panel_margin_top": 0,
    "panel_margin_bottom": 0,
    "panel_margin_left": 0,
    "panel_margin_right": 0
  }
}
```

## Hyprland
```
### Window Mode
windowrule = float true, match:class com\.kwimy\.Matuwall
windowrule = animation slide top, match:class com\.kwimy\.Matuwall
windowrule = rounding 15, match:class com\.kwimy\.Matuwall
windowrule = border_size 0, match:class com\.kwimy\.Matuwall
windowrule = rounding_power 2, match:class com\.kwimy\.Matuwall
windowrule = no_shadow on, match:class com\.kwimy\.Matuwall

### Panel Mode
layerrule = match:namespace matuwall, blur on
layerrule = match:namespace matuwall, ignore_alpha 0.5

### Backdrop
layerrule = match:namespace matuwall-backdrop, animation fade
# layerrule = match:namespace matuwall-backdrop, blur on
# layerrule = match:namespace matuwall-backdrop, ignore_alpha 0.2
```

## Theme
Theme customization is controlled from `~/.config/matuwall/config.json` under `theme`.
Optional: if `~/.config/matuwall/colors.json` exists, its color keys override `theme` colors.
Only color and radius tokens are configurable. Layout values (padding, margins, sizes) are fixed to keep scrolling and panel sizing stable.

## Style Matuwall with Matugen
1. Create a new file `matuwall-colors.json` in `~/.config/matugen/templates`
2. Add the following content to `matuwall-colors.json`:
```json
{
  "window_bg": "{{colors.background.default.rgba | set_alpha: 0.58}}",
  "text_color": "{{colors.primary.default.hex}}",
  "header_bg_start": "{{colors.background.default.rgba | set_alpha: 0.58}}",
  "header_bg_end": "{{colors.background.default.rgba | set_alpha: 0.78}}",
  "backdrop_bg": "{{colors.background.default.rgba | set_alpha: 0}}",
  "card_bg": "{{colors.secondary.dark.rgba | set_alpha: 0.04}}",
  "card_border": "{{colors.secondary.dark.rgba | set_alpha: 0.05}}",
  "card_hover_bg": "{{colors.secondary.dark.rgba | set_alpha: 0.08}}",
  "card_hover_border": "{{colors.primary.default.rgba | set_alpha: 0.2}}",
  "card_selected_bg": "{{colors.primary.default.rgba | set_alpha: 0.12}}",
  "card_selected_border": "{{colors.primary.default.rgba | set_alpha: 0.35}}"
}
```
3. Then add the following to your matugen config file `~/.config/matugen/config.toml`:
```toml
[templates.matuwall]
input_path = '~/.config/matugen/templates/matuwall-colors.json'
output_path = '~/.config/matuwall/colors.json'
```

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
- `theme.window_radius`, `theme.card_radius`, and `theme.thumb_radius` are clamped to `0..64`.
- Invalid color strings in `theme` are ignored and fallback to defaults.
- `colors.json` can override theme colors (`window_bg`, `text_color`, `header_bg_start`, `header_bg_end`, `backdrop_bg`, `card_bg`, `card_border`, `card_hover_bg`, `card_hover_border`, `card_selected_bg`, `card_selected_border`).
- If `theme.backdrop_bg` is fully transparent, Matuwall applies a tiny internal alpha so outside-click close still works in panel mode.
- `panel_mode` enables layer-shell mode (requires `gtk-layer-shell` with Gtk4 typelibs).
- `panel_edge` can be `left`, `right`, `top`, `bottom`.
- `panel_thumbs_col` is the number of thumbnails to display (width for top/bottom panels, height for left/right). If it's too large for your monitor/margins, Matuwall automatically caps visible thumbs to fit on screen.
- `panel_exclusive_zone` controls reserved space (`-1` = none). Clamped to `-1..4096`.
- `panel_margin_top` / `panel_margin_bottom` add margins in pixels (useful to sit under a top bar).
- `panel_margin_left` / `panel_margin_right` add margins for top/bottom panels.
