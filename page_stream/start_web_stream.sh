#!/bin/bash
# start_web_stream.sh
# Launch Chromium + FFmpeg + Xvfb to stream webpage as HLS

set -euo pipefail

########################################
# 1. Arguments
########################################
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <ChannelName>"
  exit 1
fi

CHANNEL_NAME="$1"
CHANNEL_ID=$(echo "$CHANNEL_NAME" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')

########################################
# 2. Paths
########################################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_FILE="$SCRIPT_DIR/../confs/web_${CHANNEL_ID}.json"
URL_FILE="$SCRIPT_DIR/web_urls/${CHANNEL_ID}.json"
HLS_DIR="$SCRIPT_DIR/hls/${CHANNEL_ID}"
PROFILE_DIR="/tmp/chrome_${CHANNEL_ID}_profile"

if [[ ! -f "$CONF_FILE" || ! -f "$URL_FILE" ]]; then
  echo "[ERROR] Missing config or URL file."
  exit 1
fi

CHANNEL_NUM=$(jq -r '.station_conf.channel_number' "$CONF_FILE")
PORT=$((8000 + CHANNEL_NUM))
URL=$(jq -r '.source_url' "$URL_FILE")

########################################
# 3. Display Settings
########################################
DISPLAY_NUM=$((90 + CHANNEL_NUM))
XVFB_DISPLAY=":$DISPLAY_NUM"
LOCK_FILE="/tmp/.X${DISPLAY_NUM}-lock"
export DISPLAY=$XVFB_DISPLAY

#Adjust Width and Height to your screen aspect ratio
WIDTH=1280
HEIGHT=720
FRAMERATE=30

echo "[INFO] Streaming: $URL on display $XVFB_DISPLAY, port $PORT"

########################################
# 4. Cleanup Setup
########################################
cleanup() {
  echo "[CLEANUP] Stopping processes..."
  pkill -f "$PROFILE_DIR" || true
  lsof -ti tcp:"$PORT" | xargs -r kill -9 || true
  kill "${CHROMIUM_PID:-}" "${FFMPEG_PID:-}" "${HTTP_PID:-}" "${XVFB_PID:-}" 2>/dev/null || true
  rm -rf "$PROFILE_DIR" "$LOCK_FILE"
  echo "[CLEANUP] Done."
}
trap cleanup EXIT

# Clear leftovers
rm -rf "$PROFILE_DIR"
mkdir -p "$HLS_DIR"

########################################
# 5. Start Xvfb
########################################
echo "[XVFB] Launching virtual display on $XVFB_DISPLAY"
Xvfb "$XVFB_DISPLAY" -screen 0 ${WIDTH}x${HEIGHT}x24 > "/tmp/xvfb_${CHANNEL_ID}.log" 2>&1 &
XVFB_PID=$!
sleep 2

########################################
# 6. Start Chromium
########################################
 #Adjust scale factor to stretch image to screen size
echo "[CHROMIUM] Launching Chromium..."
chromium-browser \
  --no-sandbox \
  --disable-gpu \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --kiosk \
  --hide-scrollbars \
  --force-device-scale-factor=1 \
  --window-size=${WIDTH},${HEIGHT} \
  --user-data-dir="$PROFILE_DIR" \
  --window-position=0,0.5 \
  "$URL" &
CHROMIUM_PID=$!
sleep 10
#--window-position=0,0 \
########################################
# 7. Screenshot Debug
########################################
echo "[DEBUG] Capturing screenshot..."
if command -v convert >/dev/null 2>&1; then
  xwd -root -display "$XVFB_DISPLAY" -out "/tmp/${CHANNEL_ID}.xwd"
  convert "/tmp/${CHANNEL_ID}.xwd" "/tmp/${CHANNEL_ID}.png" && xdg-open "/tmp/${CHANNEL_ID}.png" || echo "[WARN] Screenshot failed to open."
else
  echo "[SKIP] 'convert' not found."
fi

########################################
# 8. Start FFmpeg
########################################
echo "[FFMPEG] Starting FFmpeg..."
ffmpeg -y \
  -f x11grab -draw_mouse 0 -video_size ${WIDTH}x${HEIGHT} -i "${XVFB_DISPLAY}.0" \
  -r $FRAMERATE \
  -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2000k \
  -pix_fmt yuv420p \
  -f hls \
  -hls_time 4 -hls_list_size 6 -hls_flags delete_segments+append_list \
  -hls_segment_filename "$HLS_DIR/segment_%03d.ts" \
  "$HLS_DIR/index.m3u8" &
FFMPEG_PID=$!

########################################
# 9. Start HTTP Server
########################################
echo "[HTTP] Starting HTTP server on port $PORT"
cd "$SCRIPT_DIR"
python3 -m http.server "$PORT" &
HTTP_PID=$!

########################################
# 10. Warmup
########################################
echo "[INFO] Warming up for 10 seconds..."
sleep 10
ls -lh "$HLS_DIR"
echo "[READY] Stream available: http://localhost:$PORT/hls/${CHANNEL_ID}/index.m3u8"

########################################
# 11. Wait
########################################
wait

