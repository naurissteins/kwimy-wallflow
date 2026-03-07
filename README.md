# Matuwall

A minimal GTK4 + libadwaita wallpaper picker for Wayland compositor. Matuwall can trigger [matugen](https://github.com/InioX/matugen) to generate/apply colors from the chosen image, or run wallpaper-only mode via [awww](https://codeberg.org/LGFae/awww).

https://github.com/user-attachments/assets/5b62921e-d2a9-4f68-98fb-ad5b589e7695

- Matuwall does not manage or include [matugen](https://github.com/InioX/matugen) configuration, so you need your own matugen setup when using matugen mode.  
- If you prefer wallpaper-only mode without matugen, you can use `wall_mode_only` and `wall_awww_flags` to customize `awww` behavior. Make sure [awww](https://codeberg.org/LGFae/awww) is installed and running before use.

> [!IMPORTANT]
> Matugen `>= 4.0.0` is required for matugen mode.
> For latest Matugen on Arch Linux, install from AUR: [matugen-git](https://aur.archlinux.org/packages/matugen-git)

## 🔥 Features
- Two UI layouts: centered window mode and edge panel (layer shell) mode (`left`, `right`, `top`, `bottom`)
- Daemon first workflow with IPC controls (`--show`, `--hide`, `--toggle`, `--reload`, `--quit`, `--status`)
- Background thumbnail generation with persistent cache in `~/.cache/matuwall/`
- One-action apply flow: activate a thumbnail to run either `matugen image <wallpaper> -m <mode>` or wallpaper-only `awww img ... <wallpaper>`
- Keyboard navigation (`Enter` apply, `Esc` close, `Arrow keys` to navigate between thumbnails), plus optional mouse interaction
- Styling in `config.json` (colors + corner radius), with optional `colors.json` color override, useful for customizing appearance with your own colorscheme using matugen

> [!TIP]  
> If `"keep_ui_alive": true`, changes to `config.json`, `colors.json` or your wallpaper folder won’t take effect until you reload daemon `matuwall --reload` or restart the **matuwall** service `systemctl --user restart matuwall.service` if you're running daemon via `systemd`. 

**What `keep_ui_alive` is for and what it does**

`keep_ui_alive` controls if the picker UI stays alive in the background after you hide it.

- If it is `true`, opening Matuwall again is super fast because the UI is already loaded.
- The tradeoff is RAM usage in the background (roughly around ~200MB, can vary by setup).
- If it is `false`, the UI fully exits when hidden, so it uses less RAM, but next open is slower.

Simple rule:
- If RAM is not a big deal and you use Matuwall often, keep it `true`.
- If you don’t open Matuwall very often, keep it `false` to avoid extra background memory use.


## Installation
### AUR (Arch Linux)
```bash
yay -S matuwall
```

### Install From Source
1. Install dependencies:
```bash
sudo pacman -S --needed git python python-pip python-virtualenv python-gobject gtk4 libadwaita gtk-layer-shell
```
2. Clone and install:
```bash
git clone https://github.com/naurissteins/Matuwall.git
cd Matuwall
/usr/bin/python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
mkdir -p ~/.local/bin
ln -sf "$PWD/.venv/bin/matuwall" ~/.local/bin/matuwall
```
3. Verify install:
```bash
matuwall --status
```

## Daemon Mode
Start daemon mode once:
```
matuwall --daemon
```

Manage daemon:
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
- When `panel.panel_mode` is `true`, `--show` / `--toggle` require a running daemon/service
- If `keep_ui_alive` is `false`, the UI process exits on hide (lower idle memory)
- `config.json` is watched and reloaded by the daemon in ~0.5s; UI-only changes apply on next UI start when `keep_ui_alive` is `true`

## Panel Mode (Layer Shell)
Use panel mode to anchor Matuwall to screen edge:
```
"panel": {
  "panel_mode": true,
  "panel_edge": "left",
  "panel_thumbs_col": 3,
  "panel_margin_top": 30
}
```
`panel_thumbs_col` is treated as a requested visible count and auto-capped to monitor space, so the panel always stays fully on-screen.

## Configuration
Config file path:
- `~/.config/matuwall/config.json`

Default config:
```json
{
  "main": {
    "wallpaper_dir": "~/Pictures/Wallpapers",
    "thumbnail_size": 256,
    "thumbnail_shape": "landscape",
    "batch_size": 16,
    "window_decorations": false,
    "window_grid_cols": 3,
    "window_grid_rows": 3,
    "window_grid_max_width_pct": 80,
    "mouse_enabled": false,
    "keep_ui_alive": false
  },
  "matugen": {
    "matugen_mode": "dark",
    "matugen_type": "scheme-tonal-spot"
  },
  "wall": {
    "wall_mode_only": false,
    "wall_awww_flags": "--transition-type center --transition-step 90 --transition-fps 60 --transition-duration 2"
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
    "applied_overlay_bg": "rgba(0, 0, 0, 0.58)",
    "applied_text": "#ffffff",
    "window_radius": 15,
    "card_radius": 14,
    "thumb_radius": 10
  },
  "panel": {
    "panel_mode": false,
    "panel_edge": "left",
    "panel_thumbs_col": 5,
    "panel_exclusive_zone": -1,
    "panel_margin_top": 0,
    "panel_margin_bottom": 0,
    "panel_margin_left": 0,
    "panel_margin_right": 0
  }
}
```

## Wall Mode (Optional, no matugen)
Use wall-only mode if you want Matuwall to set wallpapers without running `matugen`.

```json
"wall": {
  "wall_mode_only": true,
  "wall_awww_flags": "--transition-type center --transition-step 90 --transition-fps 60 --transition-duration 2"
}
```

Behavior:
- `wall_mode_only = false` (default): keeps current behavior and runs `matugen image <path> -m <mode>`.
- `wall_mode_only = true`: runs `awww img <flags> <path>` and skips `matugen`.
- `wall_awww_flags` should contain only flags (no `awww img` prefix and no image path).
- The image path is injected automatically from the selected thumbnail in your `wallpaper_dir`.

Example generated command:
```bash
awww img --transition-type center --transition-step 90 --transition-fps 60 --transition-duration 2 /path/to/image.jpg
```

## Hyprland
```sh
### Matuwall daemon
# Recommended (if you use UWSM):
exec-once = uwsm app -- matuwall --daemon

# If you are not using UWSM
exec-once = matuwall --daemon

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

### Keybinds
# Toggle
bind = SUPER, W, exec, matuwall --toggle

# Reload daemon
bind = CTRL, W, exec, matuwall --reload
```

## Theme
Theme customization is controlled from `~/.config/matuwall/config.json` under `theme`.
If `~/.config/matuwall/colors.json` exists, its color keys override `theme` colors (this is optional)

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
  "card_selected_border": "{{colors.primary.default.rgba | set_alpha: 0.35}}",
  "applied_text": "{{colors.primary.default.hex}}",
  "applied_overlay_bg": "{{colors.background.dark.rgba | set_alpha: 0.90}}"
}
```
3. Then add the following to your matugen config file `~/.config/matugen/config.toml`:
```toml
[templates.matuwall]
input_path = '~/.config/matugen/templates/matuwall-colors.json'
output_path = '~/.config/matuwall/colors.json'
```

## Config Reference
### `main`
- `wallpaper_dir`: source folder for wallpapers. Supported formats: `jpg`, `jpeg`, `png`, `webp`, `bmp`, `gif`.
- `thumbnail_size`: thumbnail width, capped to `1000`.
- `thumbnail_shape`: `landscape` (16:9, default) or `square` (1:1).
- `batch_size`: thumbnails appended per UI idle cycle. Clamped to `1..128`.
- `window_grid_cols` / `window_grid_rows`: default window sizing grid. Each clamped to `1..12`.
- `window_grid_max_width_pct`: max window width as screen percent (default `80`).
- `mouse_enabled`: enables click/hover/scroll pointer interaction.
- `keep_ui_alive`: keeps UI in memory between show/hide (faster open, higher RAM use).

### `matugen`
- `matugen_mode`: mode used in `matugen image` command (for example `dark` or `light`).
- `matugen_type`: color scheme type used in `matugen image -t ...`.
  Allowed values: `scheme-content`, `scheme-expressive`, `scheme-fidelity`, `scheme-fruit-salad`, `scheme-monochrome`, `scheme-neutral`, `scheme-rainbow`, `scheme-tonal-spot`, `scheme-vibrant`.
- `matugen_contrast` (optional): passes `--contrast <value>` to matugen. Allowed range is `-1..1`.
  Leave it unset if you want matugen defaults.

### `wall`
- `wall_mode_only`: when `true`, skips matugen and uses `awww` only.
- `wall_awww_flags`: appended to `awww img` before the selected image path.

### `theme`
- `window_radius`, `card_radius`, `thumb_radius`: clamped to `0..64`.
- Invalid color strings are ignored and fallback to defaults.
- `colors.json` can override theme colors:
  `window_bg`, `text_color`, `header_bg_start`, `header_bg_end`, `backdrop_bg`, `card_bg`, `card_border`, `card_hover_bg`, `card_hover_border`, `card_selected_bg`, `card_selected_border`, `applied_overlay_bg`, `applied_text`.

### `panel`
- `panel_mode`: enables layer-shell mode (requires `gtk-layer-shell` Gtk4 typelibs).
- `panel_edge`: `left`, `right`, `top`, `bottom`.
- `panel_thumbs_col`: thumbnail count (width for top/bottom, height for left/right), auto-capped to screen space.
- `panel_exclusive_zone`: reserved space (`-1` = none), clamped to `-1..4096`.
- `panel_margin_top` / `panel_margin_bottom`: vertical margins in pixels.
- `panel_margin_left` / `panel_margin_right`: horizontal margins for top/bottom panels.
