# FieldStation42
 Broadcast TV simulator.

## Setup

Base hardware: Raspberry Pi Zero
* Install base Raspian OS
* Ensure MPV is installed and operational

### Install Circuit Python

Circuit python from Adafruit is required for listening for incoming button presses in the channel listener. You could easily substitute for gpio zero, but in my install, I am using the blinka library because it also has neopixel support. Follow instructions to install [Adafruit's Circuit Python](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi)

### Python Dependencies
Using the same virtualenv from installing circuit python, install the following:


