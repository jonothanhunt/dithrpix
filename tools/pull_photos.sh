#!/usr/bin/env bash
# Pull the dithered PNGs off the badge's LittleFS root, which disk mode
# cannot see, into ~/Downloads/dithrpix/.
set -euo pipefail
PORT=${1:-/dev/ttyACM0}
OUT=~/Downloads/dithrpix
mkdir -p "$OUT"
mpremote connect "$PORT" fs ls /photos
mpremote connect "$PORT" fs cp -r :/photos/. "$OUT/"
ls -la "$OUT"
