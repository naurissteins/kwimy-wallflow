#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="matuwall"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: missing required command: $1" >&2
    exit 1
  fi
}

require_cmd python3
require_cmd sha256sum

# Ensure PyInstaller is available in current Python environment.
python3 - <<'PY'
import importlib.util
import sys

if importlib.util.find_spec("PyInstaller") is None:
    print("Error: PyInstaller is not installed for this Python.", file=sys.stderr)
    print("Install with: python3 -m pip install pyinstaller", file=sys.stderr)
    raise SystemExit(1)
PY

# Fail fast if GI typelibs are missing on the build host.
python3 - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: F401
PY

rm -rf build dist

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "$APP_NAME" \
  --collect-data matuwall \
  --collect-submodules matuwall \
  --hidden-import gi \
  --hidden-import gi.repository.Adw \
  --hidden-import gi.repository.Gdk \
  --hidden-import gi.repository.GdkPixbuf \
  --hidden-import gi.repository.Gio \
  --hidden-import gi.repository.GLib \
  --hidden-import gi.repository.Gtk \
  matuwall/__main__.py

if head -c 4 "dist/${APP_NAME}" | grep -q '^#!'; then
  echo "Error: dist/${APP_NAME} is a script, expected an ELF binary." >&2
  exit 1
fi

if ! "dist/${APP_NAME}" --status >/dev/null 2>&1; then
  echo "Error: standalone smoke test failed (dist/${APP_NAME} --status)." >&2
  exit 1
fi

sha256sum "dist/${APP_NAME}" > "dist/checksums.txt"

echo "Built standalone binary:"
echo "  dist/${APP_NAME}"
echo "Checksum:"
echo "  dist/checksums.txt"
