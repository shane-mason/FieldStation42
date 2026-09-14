#!/usr/bin/env bash
# ==============================================================================
# FieldStation42 - Automated Headless Playout & Hardware Streaming Orchestrator
# ==============================================================================
# This script manages the entire headless broadcast pipeline inside an LXC container:
#   1. Cleans up stale IPC sockets & display locks
#   2. Initializes Xvfb (:99) virtual framebuffer (1280x720 24-bit)
#   3. Initializes PulseAudio with a persistent VirtualSink (null-sink)
#   4. Configures MPV with NVDEC hardware decoding and PulseAudio
#   5. Starts HTTP server on port 8080 serving HLS chunks
#   6. Starts FFmpeg with RTX 4090 NVENC hardware encoding (h264_nvenc)
#   7. Launches FieldStation42 field_player.py in the foreground
#   8. Traps SIGINT/SIGTERM to cleanly tear down all services on exit
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STREAM_DIR="/tmp/fs42_stream"
STREAM_PORT=8080
DISPLAY_NUM=99
DISPLAY_STR=":${DISPLAY_NUM}"
export DISPLAY="$DISPLAY_STR"

# Ensure log directory exists
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo " Starting FieldStation42 Headless Playout & Stream Service"
echo "============================================================"

# ------------------------------------------------------------------------------
# 0. Clean Up Any Lingering Processes / Sockets
# ------------------------------------------------------------------------------
echo "[1/6] Cleaning up stale sockets and processes..."
killall -9 mpv 2>/dev/null || true
rm -f /tmp/mpvsocket "/tmp/.X${DISPLAY_NUM}-lock"

# ------------------------------------------------------------------------------
# 1. Start Xvfb Virtual Framebuffer
# ------------------------------------------------------------------------------
if ! pgrep -f "Xvfb ${DISPLAY_STR}" >/dev/null 2>&1; then
    echo "[2/6] Launching Xvfb virtual display on ${DISPLAY_STR}..."
    Xvfb "${DISPLAY_STR}" -screen 0 1280x720x24 > "$LOG_DIR/xvfb.log" 2>&1 &
    sleep 1
else
    echo "[2/6] Xvfb is already running on ${DISPLAY_STR}."
fi

# ------------------------------------------------------------------------------
# 2. Setup PulseAudio & Virtual Sink
# ------------------------------------------------------------------------------
echo "[3/6] Configuring PulseAudio Virtual Sink..."
unset PULSE_SERVER
pulseaudio -D --system=false --disallow-exit --exit-idle-time=-1 2>/dev/null || true
pactl load-module module-null-sink sink_name=VirtualSink sink_properties=device.description="Virtual_Sink" 2>/dev/null || true
pactl set-default-sink VirtualSink 2>/dev/null || true
pactl unload-module module-suspend-on-idle 2>/dev/null || true
pactl set-sink-volume VirtualSink 100% 2>/dev/null || true
pactl set-sink-mute VirtualSink 0 2>/dev/null || true

# ------------------------------------------------------------------------------
# 3. Ensure MPV is Configured for NVDEC & PulseAudio
# ------------------------------------------------------------------------------
echo "[4/6] Verifying MPV hardware configuration..."
mkdir -p /etc/mpv
cat << 'EOF' > /etc/mpv/mpv.conf
ao=pulse
vo=gpu,x11
hwdec=nvdec-copy,auto
volume=100
EOF

# ------------------------------------------------------------------------------
# 4. Start HTTP Stream Server
# ------------------------------------------------------------------------------
echo "[5/6] Starting HLS HTTP server on port ${STREAM_PORT}..."
mkdir -p "$STREAM_DIR"
rm -f "$STREAM_DIR"/*
pkill -f "http.server ${STREAM_PORT}" 2>/dev/null || true
python3 -m http.server "${STREAM_PORT}" --directory "$STREAM_DIR" > "$LOG_DIR/http_stream.log" 2>&1 &
HTTP_PID=$!

# ------------------------------------------------------------------------------
# 5. Start Hardware-Accelerated FFmpeg Streamer
# ------------------------------------------------------------------------------
echo "[6/6] Launching FFmpeg hardware streamer (RTX 4090 NVENC)..."

# Select NVENC if available, fallback to ultrafast libx264
if ffmpeg -encoders 2>/dev/null | grep -q "h264_nvenc"; then
    V_ENCODER=(-c:v h264_nvenc -preset p4 -tune ll -b:v 2500k -g 60 -pix_fmt yuv420p)
else
    V_ENCODER=(-c:v libx264 -preset ultrafast -tune zerolatency -b:v 2000k -g 60 -pix_fmt yuv420p)
fi

pkill -f "ffmpeg.*${DISPLAY_STR}" 2>/dev/null || true
ffmpeg -y \
    -f x11grab -draw_mouse 0 -thread_queue_size 1024 -framerate 30 -video_size 1280x720 -i "${DISPLAY_STR}.0" \
    -f pulse -thread_queue_size 1024 -i VirtualSink.monitor \
    "${V_ENCODER[@]}" \
    -c:a aac -b:a 128k \
    -f hls -hls_time 2 -hls_list_size 5 -hls_flags delete_segments+append_list \
    "$STREAM_DIR/index.m3u8" > "$LOG_DIR/ffmpeg_stream.log" 2>&1 &
FFMPEG_PID=$!

# ------------------------------------------------------------------------------
# Cleanup Handler
# ------------------------------------------------------------------------------
cleanup() {
    echo ""
    echo "============================================================"
    echo " Shutting down FieldStation42 broadcast services..."
    echo "============================================================"
    kill "$FFMPEG_PID" 2>/dev/null || true
    kill "$HTTP_PID" 2>/dev/null || true
    killall -9 mpv 2>/dev/null || true
    rm -f /tmp/mpvsocket
    echo "Clean shutdown complete."
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# 6. Launch FieldStation42 Core Player
# ------------------------------------------------------------------------------
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
echo ""
echo "Broadcast live at: http://${HOST_IP}:${STREAM_PORT}/index.m3u8"
echo "Starting field_player.py (Press Ctrl+C to stop)..."
echo "------------------------------------------------------------"

if [ -d "env" ]; then
    source env/bin/activate
fi

python3 field_player.py
