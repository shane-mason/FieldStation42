# FieldStation42
Cable and broadcast TV simulator intended to provide an authentic experience of watching OTA television with the following goals:

* When the TV is turned on, a believable show for the time slot and network should be playing
* When switching between channels, the shows should continue playing serially as though they had been broadcasting the whole time


![An older TV with an antenna rotator box in the background](docs/retro-tv.png?raw=true)

## Features
* Supports multiple simultanous channels
* Automatically interleaves commercial break and bumps into content
* Generates weekly schedules based on per-station configurations
* Feature length content - supports movie length show blocks
* Randomly selects shows from the programming slot that have not been played recently to keep a fresh lineup
* Set dates ranges for shows (like seasonal sports or holiday shows)
* Per-station configuration of station sign-off video and off-air loops
* UX to manage catalogs and schedules
* Optional hardware connections to change the channel
* Loooing channels - useful for community bulliten channels
* Preview/guide channel with embedded video and configurable messages
    * This is a new feature - documentation in progress in the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki)
* Flexible scheduling to support all kinds of channel types
    * Traditional networks channels with commercials and bumps
    * Commercial free channels with optional end bump padding at end (movie channels, public broadcasting networks)
    * Loop channels, useful for community bulletin style channels or information loops.

![A screenshot of a guide channel simulation](docs/guide.png?raw=true)

## Alpha software - installation is not simple
This is a brand new project and in active development - installation requires some background in the following:

* Basic linux command line usage
* Reading and editing JSON configuration files
* Movie file conversion and organizing in folders

## Installation & Setup

For a complete, step-by-step guide to setting up and administering FieldStation42 software, check out the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki)

### Quickstart Setup

* Ensure Python 3 and MPV are installed on your system
* Clone the repository - this will become you main working directory.
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

# How It Works
FieldStation42 has multiple components that work together to recreate that old-school TV nostalgia.

### station_42.py
Use this to create catalogs and generate schedules. Catalogs are used to store metadata about the stations content, so they need to be rebuilt each time the content changes. Since it is inspecting files on disk, this can take some time depending on the number of videos in your content library. The liquid-scheduler uses the catalogs and the stations configuration to build schedules, so catalogs should be built first. Running `station_42.py` with no arguments will start a UI that runs in the terminal. You can use this to manage catalogs and schedules, or you can perform all operations using command line arguments with no UI. To see the list of all options, run `station_42.py --help`. 

### field_player.py
This is the main TV interface. On startup, it will read the schedule and open the correct video file and skip to the correct position based on the current time. It will re-perform this step each time the channel is changed. If you tune back to a previous channel, it will pick up the current time and start playing as though it had been playing the whole time.

The player monitors the plain text file `runtime/channel.socket` for commands to change the channel and will change to the next station configured in `main_config` in `confs/fieldStation42_conf.py` if any content is found there - or you can use the following command to cause the player to change to channel 3:

`echo {\"command\": \"direct\", \"channel\": 3} > runtime/channel.socket`

You can also open `runtime/channel.socket` in a text editor and enter the following json snippet (change 3 to whatever number you want to change to)

`{"command": "direct", "channel": 3}`

The following command will cause the player to tune up or down respectively

`{"command": "up", "channel": -1}`
`{"command": "down", "channel": -1}`

The player writes its status and current channel to `runtime/play_status.socket` - this can be monitored by an external program if needed. See [this page](https://github.com/shane-mason/FieldStation42/wiki/Changing-Channel-From-Script) for more information on intgrating with `channel.socket` and `play_status.socket`.

### command_input.py
This is provided as an example component to show how to connect an external device or program to invoke a channel changes and pass status information. This script listens for incoming commands on the pi's UART connection and then writes channel change commands to `runtime/channel.socket` 

## Using hotstart.sh
This file is for use on a running system that has been configured and testing, because it swallows output so you'll never know what's going wrong. This file is intended to be used to start the player running on system boot up.

## Connecting to a TV
The Raspberry Pi has an HDMI output, but if you want to connect it to a vintage TV, you will need to convert that to an input signal your TV can understand. If your TV has composite or RF, you can use an HTMI->Composit or HDMI->RF adapter. These units are available online or at an electronics retailer.

## Connecting a remote control or other device
Since the player can recieve external commands and publishes its status as described above, its easy to connect external devices of all kinds. See [this wiki page](https://github.com/shane-mason/FieldStation42/wiki/Changing-Channel-From-Script) for more information on intgrating with `channel.socket` and `play_status.socket`. For a detailed guide on setting up a bluetooth remote control, [see this page in the discussion boards](https://github.com/shane-mason/FieldStation42/discussions/47).


![Fritzing diagram for the system](docs/retro-tv-setup_bb.png?raw=true "Fritzing Diagram")

## Raspberry Pico Setup

This is only required if you are building the channel change detector component (not required).

* Install Circuit Python per their instructions and install dependencies for Neopixels.
* Add the contents of `aerial_listener.py` to `code.py` on the device so that it starts at boot.

The fritzing diagram shows how to connect the components together to enable channel changes.


