#!/usr/bin/env bash
set -euo pipefail

REPO="naurissteins/Matuwall"
APP="matuwall"
VERSION="latest"
PREFIX="${HOME}/.local"
INSTALL_SYSTEMD=0
DOWNLOADED_FROM=""

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

tag_candidates() {
  local value="$1"
  if [[ "$value" == "latest" ]]; then
    local latest_url latest_tag
    latest_url="$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest")"
    latest_tag="${latest_url##*/}"
    if [[ -z "$latest_tag" ]]; then
      echo "Error: failed to resolve latest release tag." >&2
      exit 1
    fi
    value="$latest_tag"
  fi

  if [[ "$value" == v* ]]; then
    printf "%s\n" "$value" "${value#v}"
  else
    printf "%s\n" "v${value}" "$value"
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
      DOWNLOADED_FROM="$url"
      return 0
    fi
  done

  echo "Error: failed to download ${APP} for version '${VERSION}'." >&2
  echo "Tried:" >&2
  printf "  - %s\n" "${urls[@]}" >&2
  return 1
}

verify_checksum_if_available() {
  local file_path="$1"
  local base_url checksums_url expected actual

  if [[ -z "$DOWNLOADED_FROM" ]]; then
    return 0
  fi

  base_url="${DOWNLOADED_FROM%/*}"
  checksums_url="${base_url}/checksums.txt"
  if ! curl -fsSL --connect-timeout 10 "$checksums_url" -o "${tmpdir}/checksums.txt"; then
    echo "No checksums.txt found for this release asset; skipping checksum verification."
    return 0
  fi

  expected="$(
    awk -v app="$APP" '
      $2 == app || $2 == "./"app || $2 ~ "/"app"$" { print $1; exit }
    ' "${tmpdir}/checksums.txt"
  )"
  if [[ -z "$expected" ]]; then
    echo "checksums.txt found but no entry for ${APP}; skipping checksum verification."
    return 0
  fi

  actual="$(sha256sum "$file_path" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo "Error: checksum verification failed for ${APP}." >&2
    echo "Expected: $expected" >&2
    echo "Actual:   $actual" >&2
    exit 1
  fi

  echo "Checksum verified (${APP})."
}

install_from_source_venv() {
  local venv_dir="${PREFIX%/}/share/${APP}/venv"
  local launcher_path="${PREFIX%/}/bin/${APP}"
  local source_tar="${tmpdir}/source.tar.gz"
  local selected_url=""

  require_cmd python3

  while IFS= read -r tag; do
    [[ -n "$tag" ]] || continue
    local url="https://github.com/${REPO}/archive/refs/tags/${tag}.tar.gz"
    if curl -fsSLI --connect-timeout 10 "$url" >/dev/null; then
      selected_url="$url"
      break
    fi
  done < <(tag_candidates "$VERSION")

  if [[ -z "$selected_url" ]]; then
    echo "Error: could not find source archive for version '${VERSION}'." >&2
    exit 1
  fi

  echo "Installing from source archive: $selected_url"
  curl -fsSL --retry 2 --connect-timeout 10 "$selected_url" -o "$source_tar"

  python3 -m venv "$venv_dir"
  "${venv_dir}/bin/pip" install --upgrade pip setuptools wheel >/dev/null
  "${venv_dir}/bin/pip" install --upgrade "$source_tar"

  mkdir -p "$(dirname "$launcher_path")"
  cat >"$launcher_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${venv_dir}/bin/python" -m matuwall "\$@"
EOF
  chmod 0755 "$launcher_path"

  echo "Installed ${APP} launcher to ${launcher_path}"
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
require_cmd sha256sum

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

bin_dir="${PREFIX%/}/bin"
bin_path="${bin_dir}/${APP}"
download_binary "${tmpdir}/${APP}"
verify_checksum_if_available "${tmpdir}/${APP}"

first_line="$(head -n 1 "${tmpdir}/${APP}" || true)"
if [[ "$first_line" =~ ^#!.*python ]]; then
  echo "Release asset is a Python launcher script; using isolated runtime install instead."
  install_from_source_venv
else
  mkdir -p "$bin_dir"
  install -m 0755 "${tmpdir}/${APP}" "$bin_path"
  echo "Installed ${APP} to ${bin_path}"
fi

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
