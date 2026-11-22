# FieldStation42

FieldStation42 turns your Linux computer or Raspberry Pi into a broadcast and cable TV simulator. Instead of picking something to watch, you flip channels. Scheduled programming plays on its own timeline, with commercials, station bumps, and all the in-between stuff that made old-school TV feel alive. Learn more at [fieldstation42.com](https://fieldstation42.com).

![A cable box next to a TV](docs/cable_cover_3.png?raw=true)
## What It Does

- **Scheduled programming** — build real TV schedules with daily lineups, prime time blocks, marathons, and seasonal programming
- **Multiple channel types** — network TV, movie channels, guide channels, radio stations, IPTV streams, and looping displays
- **Commercials and bumps** — short clips fill the breaks between shows, just like real TV
- **Web console** — configure and manage your stations from a browser
- **Web remote** — change channels and control playback from your phone or any device on the network
- **IR remote support** — use any IR remote with a Flirc USB receiver
- **On-screen display** — channel banners and now-playing info overlay on the screen
- **Extensive REST API** — control playback, change channels, query status, and build your own tools and integrations against a full HTTP API
- **Runs anywhere** — Raspberry Pi, any Linux machine, or Windows via WSL

## Documentation

Full documentation, installation guide, and channel configuration walkthroughs are at:

**[fieldstation42.com](https://fieldstation42.com)**


## Quick Start

```bash
# Install dependencies
sudo apt-get install mpv python3 python3-pip python3-venv

# Clone the repo
git clone https://github.com/shane-mason/FieldStation42
cd FieldStation42

# Run the installer
bash install.sh

# Activate the environment
source env/bin/activate

# Start the web console
python3 station_42.py
```

Then open a browser and go to `http://localhost:4242` to configure your first channel.

For the full step-by-step walkthrough, see the [Getting Started guide](https://fieldstation42.com/docs/).

![An older TV with an antenna rotator box in the background](docs/retro-tv.png?raw=true)

## Requirements

- Linux (Raspberry Pi OS Bookworm recommended, Ubuntu, Mint, Debian, or WSL on Windows)
- Python 3.10 or newer
- MPV

## Support the Project

If you're getting value from FieldStation42, consider supporting it on [Patreon](https://www.patreon.com/cw/FieldStation42). It helps keep the project active and the documentation current.

## Contributing

Bug reports, feature requests, and pull requests are welcome. Please open an issue before submitting large changes.





