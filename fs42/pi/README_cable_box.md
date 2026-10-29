# 📺 FieldStation42 Cable Box

`cable_box.py` drives a physical cable box built on a Raspberry Pi: a 3x4 matrix keypad for channel entry and a TM1637 4-digit display for the channel number and clock.

For building the box and full wiring instructions, see the [cable-box repository](https://github.com/shane-mason/cable-box), including the [Raspberry Pi 4 wiring guide](https://github.com/shane-mason/cable-box/blob/main/docs/pi4_readme.md).

## 📦 Dependencies

```bash
# Blinka (CircuitPython on Raspberry Pi) - install first:
# https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi
pip3 install adafruit-circuitpython-matrixkeypad
pip3 install raspberrypi-tm1637
```

Run it from the FieldStation42 root directory:

```bash
python3 fs42/pi/cable_box.py
```

## 🔢 Channel Entry

Type up to three digits for channels 0–999. After one or two digits the cable box waits 1.5 seconds and then tunes; a third digit tunes right away. The display shows the channel number right-aligned and zero-padded to two digits (`  05`, `  12`, ` 178`).

## 🔌 Pinout

The keypad layout is:

```
 1    2    3
 4    5    6
 7    8    9
down  0   up
```

### Default pinout

With no config file, the cable box uses these pins (BCM GPIO numbers):

| Function       | GPIO pins               |
| -------------- | ----------------------- |
| Keypad C1–C3   | 26, 20, 21              |
| Keypad R1–R4   | 5, 6, 13, 19            |
| Display CLK    | 17                      |
| Display DIO    | 18                      |
| Power button   | 3                       |

### Custom pinout: `runtime/cable_box.json`

If your build is wired differently, create `runtime/cable_box.json` with your pins. All values are **BCM GPIO numbers** (the "GPIO" numbers on a Pi pinout chart, not physical header pin numbers).

```json
{
  "keypad": { "cols": [13, 5, 26], "rows": [6, 20, 16, 19] },
  "display": { "clk": 4, "dio": 3 }
}
```

The example above is the Raspberry Pi 5 cable box wiring.

- `keypad.cols` — exactly 3 pins, in order C1, C2, C3
- `keypad.rows` — exactly 4 pins, in order R1, R2, R3, R4
- `display.clk` / `display.dio` — the TM1637 clock and data pins
- `power_button.pin` — a momentary button between this pin and ground. GPIO 3 is the default because pressing a button on GPIO 3 also starts a halted Pi.

Every section is optional. A section you include replaces that section's defaults entirely, so give all of its pins. For example, to change only the display:

```json
{
  "display": { "clk": 4, "dio": 3 }
}
```

If the file can't be read or isn't valid JSON, the cable box prints an error and falls back to the default pinout. An invalid GPIO number stops the cable box at startup with an error.

## 🌐 Server Connection

Channel changes go through the FieldStation42 server API (`/player/channels/...`), so the player must be running. By default the cable box connects to `127.0.0.1` on the `server_port` from `confs/main_config.json` (4242 if unset) and sends the `api_key` from the same file if one is set. Environment variables override these:

- `FS42_HOST` — server host (default `127.0.0.1`)
- `FS42_PORT` — server port (default `server_port`, or 4242)
- `FS42_API_KEY` — API key (default `api_key`)

## ⚙️ Other Settings

These come from `confs/main_config.json`:

- `show_cable_box_time` — show the clock on the display after 15 seconds idle (default `true`)
- `time_format` — `strftime` format for the clock (default `"%H:%M"`)
