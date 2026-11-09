import json
import logging
import math
import time
import os
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

from cable_box_input import Blink, ChannelEntry, Debounced, LongPress, MultiPress

_l = logging.getLogger("CABLEBOX")

# All pins are BCM GPIO numbers; runtime/cable_box.json overrides "keypad", "display", "power_button" and/or "led"
PINOUT_FILE = "runtime/cable_box.json"
DEFAULT_PINOUT = {
    "keypad": {"cols": [26, 20, 21], "rows": [5, 6, 13, 19]},
    "display": {"clk": 17, "dio": 18},
    # "power_button" and "led" are opt-in: the original cable box has neither wired
}

# the cable box must survive a stop so it can start things again; the remote's power button does the same
KEEP_RUNNING = {"fs42-cable-box.service", "fs42-remote-controller.service", "fs42-standby.service"}

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
            for section in ("keypad", "display", "power_button", "led"):
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


def fs42_units(*args):
    try:
        result = subprocess.run(["systemctl", "--user", *args, "fs42*", "--plain", "--no-legend"],
                                capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    names = [line.split()[0] for line in result.stdout.splitlines() if line.split()]
    return [name for name in names if name.endswith(".service") and name not in KEEP_RUNNING]


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

        self.power_button = None
        if "power_button" in pinout:
            self.power_button = digitalio.DigitalInOut(getattr(board, f"D{pinout['power_button']['pin']}"))
            self.power_button.direction = digitalio.Direction.INPUT
            self.power_button.pull = digitalio.Pull.UP

        self.led = None
        if "led" in pinout:
            self.led = digitalio.DigitalInOut(getattr(board, f"D{pinout['led']['pin']}"))
            self.led.direction = digitalio.Direction.OUTPUT
            self.led.value = False
        self.led_lit = False
        self.blink = Blink()

        self.power_debounce = Debounced(False)
        self.key_debounce = Debounced(None)
        self.press_actions = {
            2: self.start_services,
            3: self.restart_services,
            4: self.stop_services,
            5: self.show_temperature,
        }
        self.power_text = None
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
            self.stop_services()
        elif command == "direct" and channel == 98:
            self.halt()

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

    def halt(self):
        result = subprocess.run(["systemctl", "poweroff"], capture_output=True, text=True)
        if result.returncode != 0:
            _l.error(f"Halt failed: {result.stderr.strip()}")
            return False
        self.tm.show(" OFF")
        return True

    def control_services(self, action, units, label):
        if not units:
            _l.warning(f"No fs42 services to {action}")
            self.show_channel()
            return
        _l.info(f"Services {action}: {' '.join(units)}")
        self.tm.show(label)
        result = subprocess.run(["systemctl", "--user", "--no-block", action, *units], capture_output=True, text=True)
        if result.returncode != 0:
            _l.error(f"Services {action} failed: {result.stderr.strip()}")

    def start_services(self):
        if "fs42.service" in fs42_units("list-units", "--state=active"):
            _l.info("FieldStation42 is already running")
            self.show_channel()
            return
        units = fs42_units("list-unit-files", "--state=enabled") or ["fs42.service"]
        self.control_services("start", units, " On ")

    def restart_services(self):
        self.control_services("restart", fs42_units("list-units", "--state=active"), "rSt ")

    def stop_services(self):
        self.control_services("stop", fs42_units("list-units", "--state=active"), "StOP")

    def show_channel(self):
        self.tm.show(channel_label(self.channel_num) if self.channel_num >= 0 else "FS42")

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
        self.blink.flash(time.monotonic())

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
        self.tm.show(f"{get_temperature()}*")

    def on_power_presses(self, count):
        _l.info(f"Power button pressed {count} times")
        self.power_text = None
        action = self.press_actions.get(count)
        if action:
            action()
        else:
            self.show_channel()

    def on_power_hold(self):
        _l.info("Power button held, halting")
        self.power_text = None
        if not self.halt():
            self.show_channel()

    def power_feedback(self, down, now):
        if self.multi_press.held:
            remaining = math.ceil(self.long_press.hold - (now - self.long_press.down_at))
            return f"OFF{remaining}" if remaining > 0 else None
        presses = self.multi_press.count + (1 if down else 0)
        return f"P  {presses}" if presses else None

    def update_power_display(self, down, now):
        text = self.power_feedback(down, now)
        if text == self.power_text:
            return
        if text:
            self.temp_mode = False
            self.last_button_time = now
            self.tm.show(text)
        else:
            # released a hold early: put the channel back
            self.show_channel()
        self.power_text = text

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

            power_down = False
            if self.power_button:
                power_down = self.power_debounce.update(not self.power_button.value)
                self.multi_press.tick(power_down, now)
                self.long_press.tick(power_down, now)
                self.update_power_display(power_down, now)
            if self.led:
                lit = power_down or self.blink.lit(now)
                if lit != self.led_lit:
                    self.led.value = self.led_lit = lit
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
