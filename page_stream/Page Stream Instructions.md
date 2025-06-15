🌐 FieldStation42 Web Page Channel Streaming

This module enables live webpage streaming inside your FieldStation42 cable box simulator. It allows you to treat any live or dynamic webpage — such as weather maps, dashboards, or streaming sites — as a simulated TV channel. Pages are streamed using a headless Chromium browser and FFmpeg, encoded into HLS format.

🧹 Features

    Converts live websites into TV-style channels

    Streams output to http://localhost:<PORT>/hls/<channel>/index.m3u8

    Integrates directly with FieldStation42’s channel switcher

    Auto-generates configuration files and uses location metadata

    Supports multiple simultaneous web streams

📁 File Overview
File	Purpose
add_web_channel.sh	Creates a persistent, location-aware config for a new webpage channel
start_web_stream.sh	Launches a virtual display, opens Chromium, and starts FFmpeg streaming
confs/web_*.json	Stores configuration for each web stream channel
page_stream/hls/<channel>/	Temporary HLS output directory (auto-created)

✅ Requirements

Make sure the following are installed:

sudo apt update
sudo apt install -y jq curl chromium-browser ffmpeg xvfb python3 wmctrl

⚠️ Chromium must be launchable as chromium-browser. If your distro uses a different command, edit the scripts accordingly.

🚀 How to Use
📐 Adjusting Aspect Ratio, Position, and Scaling

Before diving into the streaming process, it’s important to understand how to adjust the aspect ratio, position, and scaling in the start_web_stream.sh script for the Chromium window and the FFmpeg stream.
1. Chromium Window Sizing

You can adjust the window size and position for the Chromium browser that’s used for the web stream.

    Window Size: Control the width and height of the Chromium window.

WIDTH=1280
HEIGHT=1040

Position: Define the position of the Chromium window. By default, it's set to the top-left corner (0,0).

    --window-position=0,0

2. Scaling Content

    Chromium Scaling: Use the --force-device-scale-factor to adjust the content size in the Chromium browser.

--force-device-scale-factor=1.2

FFmpeg Scaling: If you want to scale the stream output (e.g., stretch or fit the video to the screen), you can use FFmpeg's scale filter. For example:

    -filter:v "scale=1280:1040"

    This will force the video to scale to the specified resolution.

3. Aspect Ratio Adjustments

To ensure the content scales properly without distortion, maintain the aspect ratio of the stream. You can do this by adjusting both the width and height while keeping the same ratio.

Example:

    For a 16:9 aspect ratio, set the resolution to 1280x720:

WIDTH=1280
HEIGHT=720

Adjusting the scale filter in FFmpeg:

    -filter:v "scale=1280:720"

4. Fullscreen / Kiosk Mode

By default, the Chromium window is launched in kiosk mode to ensure it runs fullscreen without browser UI elements:

--kiosk

To ensure it fills the entire screen, adjust the resolution settings according to your screen size.
🧱 Step 1: Add a New Web Channel

Use the add_web_channel.sh script to generate a new channel configuration file:

./add_web_channel.sh "<URL>" "<ChannelName>" <ChannelNumber> [--force]

    <URL>: Full webpage address to stream (must work in Chromium)

    <ChannelName>: Name for the channel (e.g., Weather)

    <ChannelNumber>: Channel number for FieldStation42

    --force: (Optional) Overwrites existing configuration

Example:

./add_web_channel.sh "https://80s.myretrotvs.com/#SomeID" "80s" 80

This will:

    Create: confs/web_80s.json

    Auto-detect your location using ipinfo.io

    Create: page_stream/web_urls/80s.json

    Set up streaming to: http://localhost:8080/hls/80s/index.m3u8

▶️ Step 2: Start Streaming the Channel

Run the start_web_stream.sh script to launch the web stream:

./start_web_stream.sh "80s"

This will:

    Launch Chromium in kiosk mode on a virtual display

    Capture output using FFmpeg

    Save HLS files to: page_stream/hls/80s/

    Serve HLS over HTTP on port 8080

    Delay for warm-up before stream is available

📉 Step 3: Connect to FieldStation42

After starting the stream, make sure the confs/web_*.json file is indexed:

    Regenerate your station catalog and schedule as needed.

    Ensure your station_conf stream block looks like this:

"streams": [
  {
    "url": "http://localhost:8080/hls/80s/index.m3u8",
    "duration": 36000
  }
]

❌ Remove a Channel

To remove a channel:

pkill -f chromium-browser
pkill -f ffmpeg
rm confs/web_<channel>.json
rm -rf page_stream/hls/<channel>
rm -f page_stream/web_urls/<channel>.json

Example:

rm confs/web_80s.json
rm -rf page_stream/hls/80s
rm -f page_stream/web_urls/80s.json

📺 Stream Access

Each stream is accessible at:

http://localhost:<PORT>/hls/<channel>/index.m3u8

Where <channel> is the lowercase, underscore-safe version of the channel name.

Test with:

mpv http://localhost:8080/hls/80s/index.m3u8

💡 Tips and Notes

    Make sure no other process is using your assigned port (defaults to 8000 + channel number).

    Chromium runs in kiosk mode on a headless X session (Xvfb).

    Don’t use interactive pages that require camera/mic permissions.

    You can run multiple streams in background via & or from a launch script.

    Remember to update the FieldStation42 catalog and schedules when adding new channels.

🧪 Troubleshooting

    404 Error: Ensure your index.m3u8 is under page_stream/hls/<channel>/, and the port is correct.

    Xvfb already active: Remove lock file manually: rm /tmp/.X<display>-lock

    Port already in use: Change the port in your config and re-launch.

    No stream: Ensure Chromium is launching and content is visible inside the virtual display.

🗂️ Summary
Task	Command Example
Add new channel	./add_web_channel.sh "https://site.com" "Site" 39
Start streaming	./start_web_stream.sh "Site"
View stream	mpv http://localhost:8039/hls/site/index.m3u8
Remove channel	rm confs/web_site.json && rm -rf hls/site && pkill -f chromium
Rebuild catalog	Regenerate your FieldStation42 metadata
For full integration, make sure your new web stream channel is indexed into your station catalog and schedule files. Launch with your master script to keep everything in sync.
