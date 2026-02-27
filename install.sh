#!/usr/bin/env bash
set -euo pipefail

REPO="naurissteins/Matuwall"
APP="matuwall"
VERSION="latest"
PREFIX="${HOME}/.local"
INSTALL_SYSTEMD=0

usage() {
  cat <<EOF
Usage: $0 [options]

Install ${APP} from GitHub Releases into your local bin directory.

Options:
  --version <tag>   Install a specific release tag (default: latest)
  --prefix <path>   Install prefix (default: ~/.local)
  --systemd         Install user service file at ~/.config/systemd/user/matuwall.service
  -h, --help        Show this help
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: missing required command: $1" >&2
    exit 1
  fi
}

download_binary() {
  local out="$1"
  local -a urls=()

  if [[ "$VERSION" == "latest" ]]; then
    urls+=("https://github.com/${REPO}/releases/latest/download/${APP}")
  else
    urls+=("https://github.com/${REPO}/releases/download/${VERSION}/${APP}")
    if [[ "$VERSION" != v* ]]; then
      urls+=("https://github.com/${REPO}/releases/download/v${VERSION}/${APP}")
    else
      urls+=("https://github.com/${REPO}/releases/download/${VERSION#v}/${APP}")
    fi
  fi

  for url in "${urls[@]}"; do
    if curl -fsSL --retry 2 --connect-timeout 10 "$url" -o "$out"; then
      echo "Downloaded from: $url"
      return 0
    fi
  done

  echo "Error: failed to download ${APP} for version '${VERSION}'." >&2
  echo "Tried:" >&2
  printf "  - %s\n" "${urls[@]}" >&2
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 ]] || {
        echo "Error: --version requires a value" >&2
        exit 1
      }
      VERSION="$2"
      shift 2
      ;;
    --prefix)
      [[ $# -ge 2 ]] || {
        echo "Error: --prefix requires a value" >&2
        exit 1
      }
      PREFIX="$2"
      shift 2
      ;;
    --systemd)
      INSTALL_SYSTEMD=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_cmd curl
require_cmd install
require_cmd mktemp

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

bin_dir="${PREFIX%/}/bin"
bin_path="${bin_dir}/${APP}"
download_binary "${tmpdir}/${APP}"

mkdir -p "$bin_dir"
install -m 0755 "${tmpdir}/${APP}" "$bin_path"
echo "Installed ${APP} to ${bin_path}"

if [[ "$INSTALL_SYSTEMD" -eq 1 ]]; then
  service_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  service_path="${service_dir}/matuwall.service"
  mkdir -p "$service_dir"

  cat >"$service_path" <<EOF
[Unit]
Description=Matuwall daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
Environment=GDK_BACKEND=wayland
Environment=XDG_RUNTIME_DIR=%t
Environment=XDG_SESSION_TYPE=wayland
Environment=WAYLAND_DISPLAY=wayland-1
Environment=LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
ExecStart=${bin_path} --daemon
Restart=on-failure

[Install]
WantedBy=default.target
EOF

  echo "Installed user service: ${service_path}"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true
    echo "Run: systemctl --user enable --now matuwall.service"
  fi
fi

echo
echo "Next steps:"
echo "  ${APP} --daemon"
echo "  ${APP} --show"
echo "  ${APP} --status"
