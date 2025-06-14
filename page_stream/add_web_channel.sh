#!/bin/bash
# add_web_channel.sh
# Creates a new web streaming channel configuration

set -euo pipefail

# ---------------------
# Dependency Check
# ---------------------
REQUIRED_CMDS=("jq" "curl" "chromium-browser" "ffmpeg" "Xvfb" "python3" "wmctrl")
for cmd in "${REQUIRED_CMDS[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Required command '$cmd' is not installed or not in PATH."
    exit 1
  fi
done

# ---------------------
# Usage and Args
# ---------------------
usage() {
  echo "Usage: $0 <URL> <ChannelName> <ChannelNumber> [--force]"
  echo "Example: $0 \"https://weatherstar.netbymatt.com\" Weather 38"
  exit 1
}

if [[ $# -lt 3 ]]; then
  usage
fi

URL="$1"
CHANNEL_NAME="$2"
CHANNEL_NUMBER="$3"
FORCE=false
if [[ "${4:-}" == "--force" ]]; then
  FORCE=true
fi

# Validate channel number is numeric
if ! [[ "$CHANNEL_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] Channel number must be an integer."
  exit 1
fi

# ---------------------
# Paths
# ---------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_DIR="$SCRIPT_DIR/../confs"
URL_STORE_DIR="$SCRIPT_DIR/web_urls"
HLS_DIR="$SCRIPT_DIR/../page_stream/hls/${CHANNEL_NAME,,}"
CHANNEL_ID=$(echo "$CHANNEL_NAME" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')
CONF_FILE="${CONF_DIR}/web_${CHANNEL_ID}.json"
URL_STORE_FILE="${URL_STORE_DIR}/${CHANNEL_ID}.json"
PORT=$((8000 + CHANNEL_NUMBER))

mkdir -p "$CONF_DIR" "$HLS_DIR" "$URL_STORE_DIR"

# ---------------------
# Overwrite Check
# ---------------------
if [[ -f "$CONF_FILE" && "$FORCE" == false ]]; then
  echo "[ERROR] Configuration '$CONF_FILE' already exists. Use --force to overwrite."
  exit 1
fi

# ---------------------
# Write FieldStation42 Channel Config
# ---------------------
cat > "$CONF_FILE" << EOF
{
  "station_conf": {
    "network_name": "$CHANNEL_NAME",
    "network_type": "streaming",
    "channel_number": $CHANNEL_NUMBER,
    "runtime_dir": "runtime/${CHANNEL_ID}",
    "content_dir": "catalog/${CHANNEL_ID}_content",
    "catalog_path": "catalog/${CHANNEL_ID}.bin",
    "schedule_path": "runtime/${CHANNEL_ID}_schedule.bin",
    "network_long_name": "${CHANNEL_NAME} Channel",
    "streams": [
      {
        "url": "http://localhost:${PORT}/hls/${CHANNEL_ID}/index.m3u8",
        "duration": 36000
      }
    ]
  }
}
EOF

# ---------------------
# Write Source URL Info
# ---------------------
cat > "$URL_STORE_FILE" << EOF
{
  "channel_id": "$CHANNEL_ID",
  "channel_name": "$CHANNEL_NAME",
  "source_url": "$URL"
}
EOF

# ---------------------
# Output Summary
# ---------------------
echo "[SUCCESS] Web channel created:"
echo "  → Config file:      $(realpath "$CONF_FILE")"
echo "  → Stream directory: $(realpath "$HLS_DIR")"
echo "  → Source info:      $(realpath "$URL_STORE_FILE")"
echo "  → Launch with:      ./start_web_stream.sh \"$CHANNEL_NAME\""

