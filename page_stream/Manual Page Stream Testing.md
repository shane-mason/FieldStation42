# Manual Web Stream Testing for FieldStation42

This guide explains how to manually test the `page_stream` feature in FieldStation42. You will launch a webpage (like WeatherStar) and stream it as if it were a TV channel, without using `start_fs42.sh`.

---

## ✅ 1. Activate the Python Environment

Navigate to your project directory and activate the virtual environment:

```bash
cd /mnt/fs42drive/FieldStation42
source env/bin/activate
```

---

## ✅ 2. Create a Web Streaming Channel

Use the helper script to create a new channel configuration:

```bash
./page_stream/add_web_channel.sh "https://weatherstar.netbymatt.com/?hazards-checkbox=true&current-weather-checkbox=true&latest-observations-checkbox=true&hourly-checkbox=true&hourly-graph-checkbox=true&travel-checkbox=true&regional-forecast-checkbox=true&local-forecast-checkbox=true&extended-forecast-checkbox=true&almanac-checkbox=true&spc-outlook-checkbox=true&radar-checkbox=true&settings-wide-checkbox=false&settings-kiosk-checkbox=true&settings-scanLines-checkbox=true&settings-speed-select=1.00&settings-units-select=us&latLonQuery=Rawlins%2C+WY&latLon=%7B%22lat%22%3A41.7890116%2C%22lon%22%3A-107.2304671%7D" Weather 38
```

To overwrite an existing config:

```bash
./page_stream/add_web_channel.sh "https://weatherstar.netbymatt.com/?hazards-checkbox=true&current-weather-checkbox=true&latest-observations-checkbox=true&hourly-checkbox=true&hourly-graph-checkbox=true&travel-checkbox=true&regional-forecast-checkbox=true&local-forecast-checkbox=true&extended-forecast-checkbox=true&almanac-checkbox=true&spc-outlook-checkbox=true&radar-checkbox=true&settings-wide-checkbox=false&settings-kiosk-checkbox=true&settings-scanLines-checkbox=true&settings-speed-select=1.00&settings-units-select=us&latLonQuery=Rawlins%2C+WY&latLon=%7B%22lat%22%3A41.7890116%2C%22lon%22%3A-107.2304671%7D" Weather 38 --force
```

This generates:

* `./confs/web_weather.json`
* `./page_stream/hls/weather/`
* `./page_stream/web_urls/weather.json`

---

## ✅ 3. Start the Web Stream

Run the stream launcher manually:

From the project root:

```bash
./page_stream/start_web_stream.sh Weather
```

Or from within the `page_stream` folder:

```bash
cd page_stream
./start_web_stream.sh Weather
```

This will:

* Start Xvfb (virtual display)
* Open Chromium in kiosk mode
* Capture the display with FFmpeg
* Host the stream locally via HTTP

---

## ✅ 4. Test the Stream in MPV

Run this to check if the stream is live:

```bash
mpv http://localhost:8038/hls/weather/index.m3u8
```

To test remotely:

```bash
mpv http://<your-ip>:8038/hls/weather/index.m3u8
```

---

## 🧼 5. Stop the Stream (Optional)

To manually stop the stream:

```bash
pkill -f chrome_weather_profile
pkill -f http.server
pkill -f ffmpeg
pkill -f Xvfb
```

---

## 🛠 Tips & Troubleshooting

* **Add wide layout** to the URL for fullscreen pages:

  ```
  &settings-wide-checkbox=true
  ```
* **No video?** Make sure your stream URL exists: `ls page_stream/hls/weather/`
* **Check display status:**

  ```bash
  ps aux | grep Xvfb
  ```

---

You’re now ready to manually run and debug web-based channels in FieldStation42!

