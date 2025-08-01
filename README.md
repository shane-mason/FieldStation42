# FieldStation42

Cable and broadcast TV simulator intended to provide an authentic experience of watching OTA television with the following goals:

* When the TV is turned on, a believable show for the time slot and network should be playing
* When switching between channels, the shows should continue playing serially as though they had been broadcasting the whole time

![An older TV with an antenna rotator box in the background](docs/retro-tv.png?raw=true)

---

## 🚀 Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/shane-mason/FieldStation42.git
   cd FieldStation42
   ```
2. **Install dependencies:**
   ```bash
   ./install.sh
   ```
3. **Add your own content:**
   - Place video files in the appropriate folders (see `catalog/` and `confs/examples/`).
4. **Configure your stations:**
   - Copy an example config from `confs/examples` to `confs/` and edit as needed.
5. **Build catalogs and schedules:**
   ```bash
   python3 station_42.py --rebuild_catalog --schedule
   ```
6. **Start the player:**
   ```bash
   python3 field_player.py
   ```
7. **(Optional) Start the web server:**
   ```bash
   python3 station_42.py --server
   ```

For a full guide, see the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki).

---

## 📁 Project Structure

- `station_42.py` — Main CLI and UI for building catalogs and schedules
- `field_player.py` — Main TV interface/player
- `fs42/` — Core Python modules (catalog, schedule, API, etc.)
- `confs/` — Station and system configuration files
- `catalog/` — Your video content, organized by channel (created by installer)
- `runtime/` — Runtime files, sockets, and status (created by installer)
- `fs42/fs42_server/static/` — Web UI static files (HTML, JS, CSS)
- `docs/` — Images and documentation

---

## Features
* Supports multiple simultaneous channels
* Automatically interleaves commercial breaks and bumps into content
* Generates weekly schedules based on per-station configurations
* Feature length content - supports movie length show blocks
* To keep a fresh lineup, randomly selects shows that have not been played recently
* Set date ranges for shows (like for seasonal sports or holiday shows)
* Per-station configuration of station sign-off video and off-air loops
* User interface to manage catalogs and schedules
* Optional hardware connections to change the channel
* Built in web-based remote control
* On-Screen display with channel name, time, and date and customizable icons
* Looping channels - useful for community bulletin channels
* Preview/guide channel with embedded video and configurable messages
    * This is a new feature - documentation in progress in the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki)
* Flexible scheduling to support all kinds of channel types
    * Traditional network channels with commercials and bumps
    * Commercial-free channels with optional end bump padding at end (movie channels, public broadcasting networks)
    * Loop channels, useful for community bulletin style channels or information loops.

![A cable box next to a TV](docs/cable_cover_3.png?raw=true)

---

## 🛠️ Installation & Setup

For a complete, step-by-step guide to setting up and administering FieldStation42 software, check out the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki)

### Quickstart Setup

* Ensure Python 3 and MPV are installed on your system
* Clone the repository - this will become your main working directory.
* Run the install script
* Add your own content (videos)
* Configure your stations
    * Copy an example json file from `confs/examples` into `confs/`
* Generate a weekly schedule
    * Run `python3 station_42.py` on the command line
        * Use `--rebuild_catalog` option if content has changed
* Watch TV
    * Run `field_player.py` on the command line
* Configure start-on-boot (optional and not recommended unless you are making a dedicated device.)
    * Run `fs42/hot_start.sh` on the command line

The quickstart above is only designed to provide an overview of the required steps - use the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki) for more detailed description of the steps.

---

## How It Works
FieldStation42 has multiple components that work together to recreate that old-school TV nostalgia.

### station_42.py
Use this to create catalogs and generate schedules. Catalogs are used to store metadata about the stations content, so they need to be rebuilt each time the content changes. Since it is inspecting files on disk, this can take some time depending on the number of videos in your content library. The liquid-scheduler uses the catalogs and the stations configuration to build schedules, so catalogs should be built first. Running `station_42.py` with no arguments will start a UI that runs in the terminal. You can use this to manage catalogs and schedules, or you can perform all operations using command line arguments with no UI. To see the list of all options, run `station_42.py --help`. 

### field_player.py
This is the main TV interface. On startup, it will read the schedule and open the correct video file and skip to the correct position based on the current time. It will re-perform this step each time the channel is changed. If you tune back to a previous channel, it will pick up the current time and start playing as though it had been playing the whole time.

The player writes its status and current channel to `runtime/play_status.socket` - this can be monitored by an external program if needed. See [this page](https://github.com/shane-mason/FieldStation42/wiki/Changing-Channel-From-Script) for more information on intgrating with `channel.socket` and `play_status.socket`.

## Using hotstart.sh
This file is for use on a running system that has been configured and testing, because it swallows output so you'll never know what's going wrong. This file is intended to be used to start the player running on system boot up.

## Connecting to a TV
The Raspberry Pi has an HDMI output, but if you want to connect it to a vintage TV, you will need to convert that to an input signal your TV can understand. If your TV has composite or RF, you can use an HDMI->Composite or HDMI->RF adapter. These units are available online or at an electronics retailer.

## Connecting a remote control or other device
Since the player can recieve external commands and publishes its status as described above, it's easy to connect external devices of all kinds. See [this wiki page](https://github.com/shane-mason/FieldStation42/wiki/Changing-Channel-From-Script) for more information on intgrating with `channel.socket` and `play_status.socket`. For a detailed guide on setting up a Bluetooth remote control, [see this page in the discussion boards](https://github.com/shane-mason/FieldStation42/discussions/47).


## 🤝 How to Contribute

1. Fork this repo and create a feature branch.
2. Make your changes and add tests if possible.
3. Open a pull request describing your changes.
4. For questions, open an issue or join the [Discussions](https://github.com/shane-mason/FieldStation42/discussions).

---

## 🐞 Troubleshooting

- **Player won't start:** Check your video file paths and config files.
- **No video/audio:** Make sure MPV is installed and working from the command line.
- **Web UI not loading:** Ensure the server is running with `--server` and check your browser's dev tools for errors.
- **Database errors:** Check file permissions and that the correct Python version is used.
- For more help, see the [wiki](https://github.com/shane-mason/FieldStation42/wiki) or open an issue.

---

## 📚 Links & Resources

- [FieldStation42 Guide (Wiki)](https://github.com/shane-mason/FieldStation42/wiki)
- [API Reference](fs42/fs42_server/README.md)
- [Discussions](https://github.com/shane-mason/FieldStation42/discussions)
- [Releases](https://github.com/shane-mason/FieldStation42/releases)
- [Issues](https://github.com/shane-mason/FieldStation42/issues)

---

## Alpha software - installation is not simple
This is a fairly new project and in active development - installation requires some background in the following:

* Basic Linux command line usage
* Reading and editing JSON configuration files
* Movie file conversion and organizing in folders


