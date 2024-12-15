# FieldStation42
Broadcast TV simulator intended to provide an authentic experience of watching OTA television with the following goals:

* When the TV is turned on, a believable show for the time slot and network should be playing
* When switching between channels, the shows should continue playing serially as though they had been broadcasting the whole time

![An older TV with an antenna rotator box in the background](docs/retro-tv.png?raw=true)

## Features
* Supports multiple simultanous channels
* Automatically interleaves commercial break and bumps into content
* Generates weekly schedules based on per-station configurations
* Feature length content - supports movie length show blocks
* Randomly selects shows that have not been played recently to keep a fresh lineup
* Set dates ranges for shows (like seasonal sports or holiday shows)
* Per-station configuration of station sign-off video and off-air loops
* UX to view weekly schedules
* Optional hardware connections to change the channel

## Experimental Features - Cable Mode
* Preview/guide channel with embedded video and configurable messages
    * This is a brand new feature - documentation in progress in the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki)
* Loop channels, useful for community bulletin style channels or information loops.
    * Play videos in order from specified channels.

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

The quickstart above is only designed to provide an overview of the required step - use the [FieldStation42 Guide](https://github.com/shane-mason/FieldStation42/wiki) for more detailed description of the steps.

# How It Works
FieldStation42 has multiple components that work together to recreate that old-school TV nostalgia.

### station_42.py
This script is used to perform 2 primary tasks: build the catalog from disk (only needs to happen when content changes) and building weekly schedules. If no catalog exists, it will create one otherwise, it will just create weekly schedules for all configured channels. If a catalog exists, but you want to overwrite it (like when the channel content has been updated) use the `--rebuild_catalog` command line switch. Run this weekly via a cron job to create new schedules.

### ux.py
This script is used to view schedules for networks - it can act as a guide of sorts.

### field_player.py
This is the main TV interface. On startup, it will read the weekly schedule and open the correct video file and skip to the correct position. It will re-perform this step each time the channel is changed for the new.

### command_input.py
This is an optional component, use this to connect an external device (Raspberry Pico) to invoke a channel change. The following command will cause a channel change:

`echo anything > runtime/channel.socket`

### aerial_listener.py
This is another optional component that is used with CircuitPython on a Raspberry Pico (or similar)


## Connecting to Rasberry Pico (Optional)
If you don't want a remote button changer, like the antenna rotator box from the video, you don't need to follow this section. You can change the channel using the process above.

## Using hotstart.sh
This file is for use on a running system that has been configured and testing, because it swallows output so you'll never know what's going wrong. This file is intended to be used to start the player running on system boot up.

## Connecting to a TV
The Raspberry Pi has an HDMI output, but if you want to connect it to a vintage TV, you will need to convert that to an input signal your TV can understand. If your TV has composite or RF, you can use an HTMI->Composit or HDMI->RF adapter. These units are available online or at an electronic retailer.

![Fritzing diagram for the system](docs/retro-tv-setup_bb.png?raw=true "Fritzing Diagram")

## Raspberry Pico Setup

This is only required if you are building the channel change detector component (not required).

* Install Circuit Python per their instructions and install dependencies for Neopixels.
* Add the contents of `aerial_listener.py` to `code.py` on the device so that it starts at boot.

The fritzing diagram shows how to connect the components together to enable channel changes.


