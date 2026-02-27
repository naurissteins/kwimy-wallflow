#!/usr/bin/env bash
set -euo pipefail

APP="matuwall"
PREFIX="${HOME}/.local"
REMOVE_SYSTEMD=1

usage() {
  cat <<EOF
Usage: $0 [options]

Uninstall ${APP} from your local user paths.

Options:
  --prefix <path>    Install prefix to remove from (default: ~/.local)
  --keep-systemd     Keep ~/.config/systemd/user/matuwall.service
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ $# -ge 2 ]] || {
        echo "Error: --prefix requires a value" >&2
        exit 1
      }
      PREFIX="$2"
      shift 2
      ;;
    --keep-systemd)
      REMOVE_SYSTEMD=0
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

bin_path="${PREFIX%/}/bin/${APP}"
if [[ -f "$bin_path" ]]; then
  rm -f "$bin_path"
  echo "Removed binary: $bin_path"
else
  echo "Binary not found: $bin_path"
fi

service_path="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/matuwall.service"
if [[ "$REMOVE_SYSTEMD" -eq 1 && -f "$service_path" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now matuwall.service >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  rm -f "$service_path"
  echo "Removed service: $service_path"
fi

echo "Done. Kept user data in ~/.config/matuwall and ~/.cache/matuwall."
