# FieldStation42
 Broadcast TV simulator.

## Setup

Base hardware: Raspberry Pi Zero
* Install base Raspian OS
* Ensure MPV is installed and operational

### Install Circuit Python

Circuit python from Adafruit is required for listening for incoming button presses in the channel listener. You could easily substitute for gpio zero, but in my install, I am using the blinka library because it also has neopixel support. Follow instructions to install [Adafruit's Circuit Python](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi)

### Python Dependencies
Using the same virtualenv from installing circuit python, install the following modules.

#### moviepy
This module is used to determine the duration of a video files when building catalogs - it is not used during scheduling or live play.

`pip3 install moviepy`

#### Python MPV JSONIPC
This module is used to start and control the mpv player during playback over named pipes.

`pip3 install python-mpv-jsonipc`
