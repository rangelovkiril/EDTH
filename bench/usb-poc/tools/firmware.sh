#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cli="${ARDUINO_CLI:-.tools/arduino-cli}"
if [[ ! -x "$cli" ]]; then
  cli=arduino-cli
fi
args=()
if [[ -n "${ARDUINO_CONFIG_FILE:-}" ]]; then
  args+=(--config-file "$ARDUINO_CONFIG_FILE")
elif [[ -f .tools/arduino-s3.yaml ]]; then
  args+=(--config-file .tools/arduino-s3.yaml)
fi
board='esp32:esp32:XIAO_ESP32S3:USBMode=hwcdc,CDCOnBoot=default,PSRAM=opi'
case "${1:-build}" in
  build) "$cli" "${args[@]}" compile --fqbn "$board" --output-dir firmware/skycam/build firmware/skycam ;;
  flash)
    if [[ $# -ne 2 ]]; then
      echo 'Usage: tools/firmware.sh flash /dev/ttyACM0' >&2
      exit 2
    fi
    "$cli" "${args[@]}" upload --fqbn "$board" --port "$2" --input-dir firmware/skycam/build firmware/skycam ;;
  *) echo 'Usage: tools/firmware.sh [build | flash PORT]' >&2; exit 2 ;;
esac
