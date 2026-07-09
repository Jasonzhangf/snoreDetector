#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-}"
BIN_PATH="${2:-$ROOT_DIR/build/merged-binary.bin}"
BAUD="${BAUD:-460800}"
CHIP="${CHIP:-esp32s3}"
BEFORE_RESET="${BEFORE_RESET:-usb_reset}"
AFTER_RESET="${AFTER_RESET:-hard_reset}"

usage() {
  cat <<EOF
Usage:
  scripts/flash_zhengchen_wifi.sh /dev/cu.usbmodemXXXX [firmware.bin]

Defaults:
  firmware.bin: build/merged-binary.bin
  chip:         esp32s3
  baud:         460800

List serial ports:
  ls /dev/cu.*
EOF
}

if [[ -z "$PORT" || "$PORT" == "-h" || "$PORT" == "--help" ]]; then
  usage
  echo
  echo "Detected /dev/cu.* ports:"
  ls /dev/cu.* 2>/dev/null || true
  exit 2
fi

if [[ ! -c "$PORT" ]]; then
  echo "Serial port not found or not a character device: $PORT" >&2
  echo "Run: ls /dev/cu.*" >&2
  exit 1
fi

if [[ ! -f "$BIN_PATH" ]]; then
  echo "Firmware not found: $BIN_PATH" >&2
  echo "Build first: python scripts/release.py zhengchen-1.54tft-wifi" >&2
  exit 1
fi

if [[ ! -f "$HOME/esp/esp-idf-venv/bin/activate" ]]; then
  echo "Python venv not found: $HOME/esp/esp-idf-venv" >&2
  exit 1
fi

source "$HOME/esp/esp-idf-venv/bin/activate"
export IDF_PYTHON_ENV_PATH="$HOME/esp/esp-idf-venv"

if [[ -f "$HOME/esp/esp-idf/export.sh" ]]; then
  # Provides the ESP-IDF Python/tool environment without reinstalling anything.
  source "$HOME/esp/esp-idf/export.sh" >/dev/null
fi

echo "Flashing $BIN_PATH"
echo "Port: $PORT"
echo "Chip: $CHIP"
echo "Baud: $BAUD"
echo "Before reset: $BEFORE_RESET"
echo "After reset: $AFTER_RESET"

python -m esptool \
  --chip "$CHIP" \
  -p "$PORT" \
  -b "$BAUD" \
  --before "$BEFORE_RESET" \
  --after "$AFTER_RESET" \
  write_flash \
  --flash_mode dio \
  --flash_size 16MB \
  --flash_freq 80m \
  0x0 "$BIN_PATH"
