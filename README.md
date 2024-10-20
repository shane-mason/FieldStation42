# FieldStation42
Broadcast TV simulator intended to provide an authentic experience of watching OTA television with the following goals:

* When the TV is turned on, a believable show for the time slot and network should be playing
* When switching between channels, the shows should continue playing serially as though they had been broadcasting the whole time

![An older TV with an antenna rotator box in the backgroun](docs/retro-tv.png?raw=true)

## Features
* Supports multiple simultanous channels
* Automatically interleaves commercial break and bumps into content
* Generates weekly schedules based on per-station configurations
* Feature length content - supports movie length show blocks
* Randomly selects shows that have not been played recently to keep a fresh lineup
* Per-station configuration of station sign-off video and off-air loops
* UX to view weekly schedules
* Optional hardware connections to change the channel

## Alpha software - installation is not simple
This is a brand new project and in active development - installation requires some background in the following:

* Basic linux command line usage
* Reading and editing JSON configuration files
* Movie file conversion and organizing in folders

### Note on current limitations and roadmap
The following features are not yet supported, but are on the near-term roadmap.

* Configuring the station transition - right now it has the one behaviour, but this
    * Being able to have faster transitions is critical to emulate cable era content, so this is a P1 roadmap item
* Per time-slot commercial content


## Quickstart

* Ensure Python 3 and MPV are installed on your subsystem
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


## How Content is Structured
FieldStation42 uses a directory (folder) structure to tag content per station. Each station has a content directory (folder) specified in its configuration. FieldStation42 will scan the content directory and build a catalog based on movie files found in the directories. For example, a content directory may have the following sub-folders:

* MyStationContent
    * bumps
    * cartoon
    * commercials
    * daytime
    * late
    * morning
    * primetime
    * sports

The channel configuration will use the directory names as 'tags' to schedule based on the channel configuration - see below for details.

### Sub-Directories (Sub-Folders) in content directories
When content directories contain sub-folders, they will be scanned for mp4 media and added to the tags content. Movie files in these directories will be treated like content from the main directory. This feature is useful for mixing in seasonal or holiday content as well as for combining content from multiple sources.

### About content format and duration
The program expects content to have an mp4 extension, though this could easily be extended if there are use cases.

FieldStation42 uses one-hour show blocks by default - which can be made up of two shows that are under 30 minutes each or multiple clips stitched together. Feature length blocks of up to 2 hours are supported in folders listed in the 'two_hour' configuration for each station.

# Insall & Setup Process

FieldStation42 is in-development, so the install process takes multiple steps.

## Install Dependencies
Any linux installation should work fine (including Rasberry Pi) and it even works with windows subsystem for linux.

* Ensure MPV is installed and operational
    * `sudo apt-get install mpv`
* Ensure Python 3 is installed and up-to-date
    * `sudo apt-get install python3`

## Clone Repository
Use the standard github command to clone the repository into a local directory.


## Run install.sh
Change to the newly cloned repo folder and run:

`./install.sh`

This will install python dependencies and create runtime and catalog folders.

## Configuring Stations
For simplicity, configurations are stored as python files in the 'confs' module.

### fieldStation42_conf.py
The main configuration is `confs/fieldStation42_conf.py` - its main job is to load json configuration files in the same directory. You should not need to edit this file unless you have a specific reason to. It will search for json files in the confs folder and will load those as stations. There are examples in `confs/examples` that can be copied into this `confs/` folder as the starting point for a channel configuration.

### Per Channel Configurations
Each channel is a separate json file. Example configurations are provided in the `confs/examples` directory. Just copy the example json up into the `confs/` directory.
```
{station_conf : {
    # basic human readable name for the channel
    'network_name' : "MyChannel",
    # path to the catalog binary file to be stored
    'catalog_path' : "catalog/mychannel_catalog.bin",
    # root directory for content for this station
    'content_dir' : "catalog/mychannel_catalog",
    # runtime dir for this station - where schedules etc will be stored
    'runtime_dir' : "runtime/mychannel",
    # path to output the weekly schedule
    'schedule_path': "runtime/mychannel_schedule.bin",
    # must be inside or linked inside content_dir - these will be used to pad time in the video stream
    'commercial_dir' : "commercial",
    # must be inside or linked inside content_dir - these will be used to pad time in the video stream
    'bump_dir' : "bump",
    # list of directories (tags) intended to be stitched clips vs full content in a single file
    'clip_shows' : ["some_show", "some_clip_show"],
    # list of directories that contain content between one and two hours
    "two_hour" : ["movie", "documentary"],
    #used at sign-off time (played once)
    'sign_off_video': "catalog/anthem_signoff.mp4",
    #used when the channel is offair
    'off_air_video': "catalog/off_air_pattern.mp4",
...
```

Note: Previous versions used python modules instead of json files. This still works, but may stop working in future versions.

Note on tags listed in `two_hour` slots - these videos can be any length under 2 hours. The shorter they are, the more commercials and bumps that will be added to pad.

#### Schedule Configuration
Schedules are configured in the `'monday'` through ``sunday'` elements of station_conf and have the following structure:

```
    'monday': {
        # will play random content from the content/morning path
        '7': {'tags': 'morning'},
        # will play random content from the content/morning path
        '8': {'tags': 'morning'},
        # will play random content from the content/cartoon path
        '9': {'tags': 'cartoon'},
        # will play random content from the content/gameshow path
        '10': {'tags' : 'gameshow'},
        '11': {'tags' : 'gameshow'},
        '12': {'tags' : 'daytime'},
        '13': {'tags' : 'daytime'},
        '14': {'tags' : 'daytime'},
        '15': {'tags' : 'classic'},
        # since movie was listed as a two_hour tag, the next hour can be ignored
        '16': {'tags' : 'movie'},
        '17': {"continued": true},
        '18': {'tags' : 'news'},
        '19': {'tags' : 'gameshow'},
        '20': {'tags' : 'sitcom'},
        # since this is a clip show, will stitch random clips from content/some_clip_show
        '21': {'tags' : 'some_clip_show'},
        '22': {'tags' : 'prime'},
        '23': {'tags' : 'news'},
        '0': {'tags' : 'late'},
        '1': {'tags' : 'late-late'},
        '2': {'tags' : 'classic'}
        '3': {'event' : 'signoff'}
    },
```
In generalized terms, we use a scheme where the hours number is used as the key and the value points to a 'tag' or path of the form: `content/tag`

### About station runtime directories
This is where each stations schedule will be stored and read from. You will need to create these directories if they do not exist.

### About Station Catalogs
Station catalogs are a binary representation of the video files stored in the stations content directories. When weekly schedules are being created, if a stations does not have a catalog.bin file, one will be created by recursively searching the stations configured `content_dir` for mp4 files. Each video file is inspected for length and other metadata and stored by indexed tags (directory names) in the station's configured `catalog_path`.

*NOTE:* If you update your content, you will need to rebuild the catalog using `station_42.py` with th `--rebuild_catalog` option specified.

### About Sign Off events
A signoff event is specified by assigning a time slot to `{'event' : 'signoff'}` and will cause the video file specified by `sign_off_video` to be played once at the top of the hour. If `off_air_video` is specified, then the remainder of the hour will be filled by looping `off_air_video`.

### About Off Air time
If a time slot is not specified, it will be considered as off-air for schedule creation. If `off_air_video` is specified, then the slot will be filled by looping `off_air_video`.

## Building Weekly Schedules
Station schedules span Monday-Sunday and are stored in the station's configured `runtime_dir`

To build the schedule, run:

`python3 station_42.py`

This process will load each stations catalog and uses the schedule configuration to build a series of .json files in the station's configured `runtime_dir` of the form `day_hour.json` - for example: saturday_10.json would be the schedule for saturday at 10:00 am. These json files are essentially playlists that relate directly to the `saturday`->`10`; a random video with a low play count from the directory specified by the tag will be picked as the base video. If it is less than 30 minutes long, a second video will be selected from the same directory to round out the hour. Commercials and station bumps cut into playlist to build out to the full hour timeslot. Several different scheduling strategies are used to cut-in commercials and bumps, depending on the amount of time needed to fill. Selected shows have their playcounts incremented so they are less likely to be selected next.

The following shows an example start for an hourly scheduling block. The base video here is `some_cartoon_V1-003.mp4` and it will play for 440 seconds before 3 commercials will come on. Then, `some_cartoon_V1-003.mp4` will be started where it left off and play for 440 seconds, before another commercial break will start.

```
    [
    {
        "path": "catalog/mystation_catalog/cartoon/some_cartoon_V1-0003.mp4",
        "start": 0,
        "duration": 440.3
    },
    {
        "path": "catalog/mystation_catalog/commercial/comx00022985.mp4",
        "start": 0,
        "duration": 30.76
    },
    {
        "path": "catalog/mystation_catalog/bump/com00096765.mp4",
        "start": 0,
        "duration": 20.72
    },
    {
        "path": "catalog/mystation_catalog/bump/com00077020.mp4",
        "start": 0,
        "duration": 20.17
    },
    {
        "path": "catalog/mystation_catalog/cartoon/some_cartoon_V1-0003.mp4",
        "start": 440.3,
        "duration": 440.3
    },
    {
        "path": "catalog/mystation_catalog/bump/com00057040.mp4",
        "start": 0,
        "duration": 23.6
    },
...
```

*NOTE:* The catalog is not rebuilt from the content directory each time you run `station_42.py` since it can take a long time on large collections. If you update your content, you will need to rebuild the catalog using `station_42.py` with th `--rebuild_catalog` option specified. This will cause the program to ignore the catalog file on disk and construct a new catalog.

```python3 station_42.py --rebuild_catalog```

## Starting the player
To start the player, run:

`python3 field_player.py`

It will automatically start playing the scheduled content for the first station configured in `main_config` in `confs/fieldStation42_conf.py`

Note: This will fail if you have not already generated a weekly schedule using `station_42.py`

### Changing the station
The player listen to the file specified by `channel_socket` in `confs/fieldStation42_conf.py` for commands to change the channel. To change the channel, just open the file that file in any text editor and save any text (doesnt matter what). The field_player monitors this file and will change to the next station configured in `main_config` in `confs/fieldStation42_conf.py`- or you can use the following command to cause a channel change:

`echo anything > runtime/channel.socket`

## Connecting to Rasberry Pico (Optional)
If you don't want a remote button changer, like the antenna rotator box from the video, you don't need to follow this section. You can change the channel using the process above.

## Using hotstart.sh
This file is for use on a running system that has been configured and testing, because it swallows output so you'll never know what's going wrong. This file is intended to be used to start the player running on system boot up.

![Fritzing diagram for the system](docs/retro-tv-setup_bb.png?raw=true "Fritzing Diagram")

## Raspberry Pico Setup

This is only required if you are building the channel change detector component (not required).

* Install Circuit Python per their instructions and install dependencies for Neopixels.
* Add the contents of `aerial_listener.py` to `code.py` on the device so that it starts at boot.

The fritzing diagram shows how to connect the components together to enable channel changes.


