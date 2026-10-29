import json
import logging
import time
import os
import sys
import subprocess

import requests

# Uses adafruit circuitpython via Blink - install blinka first:
# https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi
# pip3 install adafruit-circuitpython-matrixkeypad
import digitalio
import adafruit_matrixkeypad
import board

# also requires tm1673 library:
# pip3 install raspberrypi-tm1637
import tm1637

from cable_box_input import ChannelEntry, Debounced, LongPress, MultiPress

_l = logging.getLogger("CABLEBOX")

# All pins are BCM GPIO numbers; runtime/cable_box.json overrides "keypad", "display" and/or "power_button"
PINOUT_FILE = "runtime/cable_box.json"
DEFAULT_PINOUT = {
    "keypad": {"cols": [26, 20, 21], "rows": [5, 6, 13, 19]},
    "display": {"clk": 17, "dio": 18},
    # GPIO 3 is the pin that wakes a halted Pi
    "power_button": {"pin": 3},
}

TICK = 0.02
POLL_INTERVAL = 0.1
REFRESH_INTERVAL = 1.0


def load_pinout():
    pinout = dict(DEFAULT_PINOUT)
    if os.path.exists(PINOUT_FILE):
        _l.info(f"Loading pinout from {PINOUT_FILE}")
        try:
            with open(PINOUT_FILE) as fp:
                overrides = json.load(fp)
            for section in ("keypad", "display", "power_button"):
                if section in overrides:
                    pinout[section] = overrides[section]
        except Exception as e:
            _l.error(f"Error loading pinout from {PINOUT_FILE}, using defaults: {e}")
            pinout = dict(DEFAULT_PINOUT)
    return pinout


def get_temperature():
    a = str(subprocess.check_output(["vcgencmd", "measure_temp"]))
    _l.debug(f"Temperature reading: {a}")
    b = a.split("=")[1]
    c = float(b.split("'")[0])
    # output in form: temp=49.4'C
    f = round((c * 1.8) + 32)
    return f
    # return c


def channel_label(num):
    return f"{num:02d}".rjust(4)


class CableBox:
    def __init__(self, status_socket="runtime/play_status.socket", press_socket="runtime/press.socket"):
        self.status_socket = status_socket
        self.press_socket = press_socket

        pinout = load_pinout()

        self.tm = tm1637.TM1637(clk=pinout["display"]["clk"], dio=pinout["display"]["dio"])
        self.tm.brightness(0)
        self.tm.show("FS42")

        column_pins = [digitalio.DigitalInOut(getattr(board, f"D{n}")) for n in pinout["keypad"]["cols"]]
        row_pins = [digitalio.DigitalInOut(getattr(board, f"D{n}")) for n in pinout["keypad"]["rows"]]

        # Define keypad layout
        keys = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("down", "0", "up"))

        self.keypad = adafruit_matrixkeypad.Matrix_Keypad(row_pins, column_pins, keys)

        self.power_button = digitalio.DigitalInOut(getattr(board, f"D{pinout['power_button']['pin']}"))
        self.power_button.direction = digitalio.Direction.INPUT
        self.power_button.pull = digitalio.Pull.UP

        self.power_debounce = Debounced(False)
        self.key_debounce = Debounced(None)
        self.press_actions = {4: self.show_temperature}
        self.multi_press = MultiPress(self.on_power_presses)
        self.long_press = LongPress(self.on_power_hold)
        self.entry = ChannelEntry(self.on_step, self.on_digits, self.on_direct)

        self.channel_num = 0
        self.last_stat = ""

        # mode to display and update temp
        self.temp_mode = False
        self.last_button_time = time.monotonic()

        self.show_time = True
        self.time_format = "%H:%M"
        config = {}
        try:
            with open("confs/main_config.json") as fp:
                config = json.load(fp)
                self.show_time = config.get("show_cable_box_time", True)
                self.time_format = config.get("time_format", "%H:%M")
        except Exception:
            pass

        host = os.getenv("FS42_HOST", "127.0.0.1")
        port = os.getenv("FS42_PORT", config.get("server_port", 4242))
        self.base_url = f"http://{host}:{port}"
        api_key = os.getenv("FS42_API_KEY") or config.get("api_key")
        self.api = requests.Session()
        if isinstance(api_key, str) and api_key.strip():
            self.api.headers["X-API-Key"] = api_key.strip()

    def send_command(self, command, channel=-1):
        if command == "direct" and channel == 99:
            # then we want to shut the player down
            os.system("pkill -SIGINT -f field_player.py")
            sys.exit(0)
        elif command == "direct" and channel == 98:
            # then we want to shutdown and halt the system
            os.system("pkill -9 -f field_player.py")
            os.system("killall mpv")
            os.system("sudo halt")
            sys.exit(-1)

        elif command == "direct" and channel == 97:
            # temp = get_temperature()
            # self.tm.show(f"{temp}*")
            self.temp_mode = True
        else:
            target = channel if command == "direct" else command
            _l.info(f"Sending channel command: {target}")
            try:
                response = self.api.get(f"{self.base_url}/player/channels/{target}", timeout=2)
                if not response.ok:
                    _l.warning(f"Channel command {target} failed: {response.status_code} {response.text}")
            except requests.RequestException as e:
                _l.warning(f"Channel command {target} failed: {e}")

    def check_status(self):
        new_stat = None
        with open(self.status_socket) as fp:
            as_str = fp.read()

            if as_str != self.last_stat:
                _l.info(f"Status changed: {as_str}")
                self.last_stat = as_str
                try:
                    new_stat = json.loads(as_str)
                except:
                    # assume that it was a partial read and try again next time
                    _l.warning(f"Error decoding status: {as_str}")
        return new_stat

    def check_press(self):
        try:
            with open(self.press_socket) as fp:
                as_str = fp.read().strip()
            if not as_str:
                return None
            data = json.loads(as_str)
            with open(self.press_socket, "w") as fp:
                fp.write("")
            if time.time() - data["ts"] < 2.0:
                return data["digits"]
        except Exception:
            pass
        return None

    def read_keys(self):
        pressed = self.keypad.pressed_keys
        if len(pressed) == 1:
            return pressed[0]
        return None

    def key_touched(self, key):
        _l.info(f"Key pressed: {key}")
        self.temp_mode = False
        self.last_button_time = time.monotonic()
        self.tm.show("    ")

    def on_step(self, direction):
        self.key_touched(direction)
        if direction == "up":
            self.send_command("up")
            self.channel_num += 1
            self.tm.show("----")
        elif self.channel_num > 0:
            self.send_command("down")
            self.channel_num -= 1
            self.tm.show("----")

    def on_digits(self, number):
        self.key_touched(number)
        self.tm.show(channel_label(number))

    def on_direct(self, channel):
        _l.info(f"Applying selection {channel}")
        self.tm.show(channel_label(channel))
        self.channel_num = channel
        self.send_command("direct", channel)

    def show_temperature(self):
        self.last_button_time = time.monotonic()
        self.temp_mode = True

    def on_power_presses(self, count):
        _l.info(f"Power button pressed {count} times")
        action = self.press_actions.get(count)
        if action:
            action()

    def on_power_hold(self):
        _l.info("Power button held")

    def poll_player(self):
        if not self.entry.active:
            remote_digits = self.check_press()
            if remote_digits:
                self.last_button_time = time.monotonic()
                self.tm.show(channel_label(int(remote_digits)))

        new_stat = self.check_status()
        if new_stat:
            self.temp_mode = False
            try:
                new_channel_num = int(new_stat["channel_number"])
                if new_channel_num != self.channel_num:
                    self.last_button_time = time.monotonic()
                    self.channel_num = new_channel_num
                if self.channel_num >= 0:
                    self.tm.show(channel_label(self.channel_num))
                    _l.info(f"Set channel: {self.channel_num}")
                else:
                    self.tm.show("FS42")
            except:
                self.tm.show("FS42")

    def refresh_display(self, now):
        if self.show_time and now - self.last_button_time > 15 and not self.entry.active:
            formatted = time.strftime(self.time_format, time.localtime())
            if ":" in formatted:
                h, m = formatted.split(":", 1)
                self.tm.numbers(int(h), int(m))
            else:
                self.tm.show(formatted)
        elif self.temp_mode:
            temp = get_temperature()
            self.tm.show(f"{temp}*")

    def event_loop(self):
        last_poll = 0
        last_refresh = 0
        while True:
            now = time.monotonic()

            power_down = self.power_debounce.update(not self.power_button.value)
            self.multi_press.tick(power_down, now)
            self.long_press.tick(power_down, now)
            self.entry.tick(self.key_debounce.update(self.read_keys()), now)

            if now - last_poll >= POLL_INTERVAL:
                last_poll = now
                self.poll_player()

            if now - last_refresh >= REFRESH_INTERVAL:
                last_refresh = now
                self.refresh_display(now)

            time.sleep(TICK)

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO)
    cable_box = CableBox()
    cable_box.event_loop()
