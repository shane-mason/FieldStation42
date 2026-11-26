#!/usr/bin/env python3
import argparse
import glob
import json
import logging
import os
import re
import select
import shutil
import threading
import time
from typing import Callable, Dict

import requests
import subprocess
import sys
from evdev import InputDevice, ecodes

logging.basicConfig(format='%(name)s: %(message)s', level=logging.DEBUG)


class ButtonNames:
    POWER_DOWN = 'power_down'
    POWER_UP = 'power_up'
    POWER_TOGGLE = 'power_toggle'
    LEFT = 'navigation_left'
    RIGHT = 'navigation_right'
    UP = 'navigation_up'
    DOWN = 'navigation_down'
    ENTER = 'confirm'
    CHANNEL_UP = 'channel_up'
    CHANNEL_DOWN = 'channel_down'
    VOLUME_UP = 'volume_up'
    VOLUME_DOWN = 'volume_down'
    MUTE = "mute"
    BACK = 'last_channel'
    GUIDE = 'show_guide'
    TOGGLE_SUBTITLES = 'toggle_subtitles'
    CYCLE_SUBTITLES = 'cycle_subtitles'
    CYCLE_AUDIO = 'cycle_audio'
    EXIT = 'exit'  # used only for FLIRC remote
    NUMBER_PREFIX = 'number_'  # don't forget to add the digit!


class BaseRemote:
    """A base class for remote control. At its simplest, it raises named events representing
    buttons when the underlying remote detects them. Things such as button de-bouncing should
    take place with a remote's class, and the main remote class should take button events and
     dispatch the various API calls to perform the actions"""

    # event callbacks should pass BUTTON NAMES
    def __init__(self):
        self.button_callback: Callable[[str], bool] = None
        """The event raised when a button is pressed. 
        
        Returns: True if the event was processed, False otherwise.
        """

    def run_forever(self):
        pass


class TestModeRemote(BaseRemote):
    def __init__(self):
        super().__init__()

    def run_forever(self):
        """Run in test mode using stdin for input (for WSL/development)"""
        print("\n" + "=" * 60)
        print("TEST MODE - Running without input device")
        print("=" * 60)
        print("\nAvailable commands:")
        print("  0-9: Channel selection")
        print("  h: Home/Guide")
        print("  u: Channel up")
        print("  d: Channel down")
        print("  l: Volume down (left)")
        print("  r: Volume up (right)")
        print("  m: Mute")
        print("  b: Last channel")
        print("  e: Power/End (toggle services)")
        print("  q: Quit")
        print("\nType a command and press Enter:")
        print("=" * 60 + "\n")

        while True:
            try:
                cmd = input("> ").strip().lower()

                if not cmd:
                    continue

                # Handle numbers
                if cmd.isdigit():
                    for digit in cmd:
                        self.button_callback(f"{ButtonNames.NUMBER_PREFIX}{digit}")
                    continue

                # Map single character commands to key names
                key_map = {
                    'h': ButtonNames.GUIDE,
                    'u': ButtonNames.CHANNEL_UP,
                    'd': ButtonNames.CHANNEL_DOWN,
                    'l': ButtonNames.VOLUME_DOWN,
                    'r': ButtonNames.VOLUME_UP,
                    'm': ButtonNames.MUTE,
                    'b': ButtonNames.BACK,
                    'e': ButtonNames.POWER_TOGGLE,
                    'q': ButtonNames.EXIT,
                }

                key_name = key_map.get(cmd)
                if key_name:
                    if not self.button_callback(key_name):
                        break
                else:
                    print(f"Unknown command: {cmd}")

            except KeyboardInterrupt:
                print("\nExiting remote controller...")
                break
            except EOFError:
                break


class FlircRemote(BaseRemote):
    # Debounce Configuration - Time in seconds to wait between repeated button presses
    DEBOUNCE_TIME = 0.25  # 250ms default debounce time
    # Key Mappings - Change these to customize which keys do what
    # Available key names: 'home', 'end', 'up', 'down', 'left', 'right', 'space', 'enter',
    # 'esc', 'tab', 'backspace', 'delete', 'insert', 'pageup', 'pagedown', 'f1'-'f12',
    # 'a'-'z', 'leftshift', 'rightshift', 'leftctrl', 'rightctrl', 'leftalt', 'rightalt'
    DEFAULT_KEY_MAPPINGS = {
        # Remote control functions
        'show_guide': 'home',  # Show program guide
        'volume_up': 'right',  # Increase volume
        'volume_down': 'left',  # Decrease volume
        'channel_up': 'up',  # Next channel
        'channel_down': 'down',  # Previous channel
        'navigation_up': 'pageup',  # Up / next item on web channels (guide, PPV)
        'navigation_down': 'pagedown',  # Down / previous item on web channels (guide, PPV)
        'navigation_left': 'leftbrace',  # [ - Left on web channels (guide)
        'navigation_right': 'rightbrace',  # ] - Right on web channels (guide)
        'confirm': 'enter',  # Select item on web channels (guide, PPV)
        'last_channel': 'backspace',  # Switch to last channel
        'mute': 'm',  # Mute/unmute volume
        'toggle_subtitles': 'v',  # Toggle subtitle visibility in mpv
        'cycle_subtitles': 'j',  # Cycle subtitle tracks in mpv
        'cycle_audio': 'a',  # Cycle audio tracks in mpv
        'power_stop': 'end',  # Stop player (power button)
        'exit': 'esc',  # Exit remote controller

        # Alternative mappings (uncomment to use):
        # 'power_stop': 'space',     # Use spacebar for power/stop
        # 'show_guide': 'g',         # Use 'g' key for guide
        # 'volume_up': 'pageup',     # Use page up for volume up
        # 'volume_down': 'pagedown', # Use page down for volume down
    }

    def __init__(self, device: InputDevice, file_mapping: Dict[str, str]):
        super().__init__()
        self._logger = logging.getLogger('flirc_remote')
        self._last_press_time = {}
        self._device = device
        # Debounce tracking - stores last press time for each function
        self._debounce_lock = threading.Lock()
        self._input_lock = threading.Lock()

        # load overrides provided from JSON config
        self._key_mappings = self.DEFAULT_KEY_MAPPINGS.copy()
        for function, key in file_mapping.items():
            self._key_mappings[function] = key

    def run_forever(self):
        for event in self._device.read_loop():
            if not self.handle_key_event(event):
                return

    def should_allow_press(self, function_name, debounce_time=DEBOUNCE_TIME):
        """Check if enough time has passed since last press of this function"""
        with self._debounce_lock:
            current_time = time.time()
            last_time = self._last_press_time.get(function_name, 0)

            if current_time - last_time >= debounce_time:
                self._last_press_time[function_name] = current_time
                return True
            else:
                return False

    def get_key_name_from_code(self, key_code):
        name = ecodes.KEY.get(key_code)

        self._logger.debug(f"Key code: {key_code}")

        if name is None:
            self._logger.debug(f"Unknown key")
            return str(key_code)

        # evdev can return multiple names for the same key code
        if isinstance(name, (tuple, list)):
            self._logger.debug(f"Key aliases: {name}")

            # Filter for meaningful key name
            preferred = [
                n for n in name
                if not n.endswith("_MIN_INTERESTING")
                   and not n.endswith("_MAX_INTERESTING")
            ]

            if preferred:
                name = preferred[0]
            else:
                name = name[0]

        self._logger.debug(f"Key name: {name}")

        return name.removeprefix("KEY_").lower()

    def handle_key_event(self, event):
        """Handle key press events from evdev"""
        if event.type == ecodes.EV_KEY and event.value == 1:  # Key press (not release)
            key_code = event.code

            # Number keys (1-9, 0) - always handled the same way
            if ecodes.KEY_1 <= key_code <= ecodes.KEY_9:
                number = key_code - ecodes.KEY_1 + 1
                self.button_callback(ButtonNames.NUMBER_PREFIX + str(number))
                return True
            elif key_code == ecodes.KEY_0:
                self.button_callback(ButtonNames.NUMBER_PREFIX + "0")
                return True
            elif key_code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
                self.button_callback(ButtonNames.ENTER)

            # Get the key name and check if it's mapped to a function
            if key_code == ecodes.KEY_KPENTER:
                key_name = 'enter'
            else:
                key_name = self.get_key_name_from_code(key_code)
            if not key_name:
                self._logger.debug(f"Unknown key code: {key_code}")
                return True

            self._logger.debug(f"Key pressed: {key_name} (code: {key_code})")
            return self.button_callback(key_name)

        return True


class FlircRemoteAllDevices(FlircRemote):
    """A wrapper over FlircRemote that listens to all udev event sources"""

    def __init__(self, mapping: Dict = {}):
        super().__init__(None, mapping)
        self._device_remotes = {}

    def run_forever(self):
        devices = {}

        try:
            while True:
                # Discover newly connected devices
                for device_path in glob.glob('/dev/input/event*'):
                    if device_path in devices:
                        continue

                    try:
                        device = InputDevice(device_path)

                        if ecodes.EV_KEY not in device.capabilities():
                            continue

                        device.grab()
                        devices[device_path] = device

                        self._logger.debug(f"Listening to device: {device.name} ({device.path})")

                    except (OSError, PermissionError):
                        # Device may have disconnected between glob() and InputDevice()
                        continue

                if not devices or len(devices) == 0:
                    self._logger.debug("No keyboard/remote devices found. Waiting...")
                    time.sleep(5)
                    continue

                try:
                    readable, _, _ = select.select(
                        list(devices.values()),
                        [],
                        [],
                        1.0
                    )

                    for device in readable:
                        try:
                            for event in device.read():
                                if not self.handle_key_event(event):
                                    return

                        except FileNotFoundError:
                            self._logger.warning(f"Input device missing: {device.name}")

                            try:
                                device.ungrab()
                            except OSError:
                                pass

                            devices.pop(device.path, None)

                        except OSError as e:
                            if e.errno == 19 or e.errno == 2:
                                self._logger.info(f"Input device disconnected: {device.name}")

                                try:
                                    device.ungrab()
                                except OSError:
                                    pass

                                devices.pop(device.path, None)
                            else:
                                raise

                except FileNotFoundError:
                    # A device disconnected while select/read was operating.
                    continue

        except PermissionError:
            print("Permission denied. Try running with sudo.")
            sys.exit(1)

        except KeyboardInterrupt:
            print("\nExiting remote controller...")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

        finally:
            # Release devices
            for device in devices.values():
                try:
                    device.ungrab()
                except OSError:
                    pass


class HdmiCecRemote(BaseRemote):
    # to use this, first install cec-client:
    # apt-get install cec-utils

    # IMPORTANT
    # add vc4.force_hotplug=3 to /boot/firmware/cmdline.txt
    # otherwise your display will randomly turn on by itself.

    # We'll wrap cec-client instead of using cec/libcec directly because:
    #  1) python libcec doesn't fully expose the entirety of libcec, and so
    #     I have been unable to convince my connected TV that Station42 is a tuner,
    #     and so the channel buttons don't work, which I'd like them to.
    #  2) libCEC proper has its own python wrapper which is full-featured generated from
    #     SWIG, however it doesn't ship with the libcec .deb files.
    #  Doing this achieves everything desired with minimal hassle.
    key_up_regex = re.compile(r"key released: .*\((\d+)\) D:(\d+)")
    power_up_regex = re.compile(r"powering on 'TV'")
    power_up_regex_alternate = re.compile(r"power status changed from '.+' to '.+on'")
    power_off_regex = re.compile(r"power status changed from '.+' to 'standby'")

    _button_to_function = {
        0x00: ButtonNames.ENTER,  # CEC_USER_CONTROL_CODE_SELECT
        0x01: ButtonNames.UP,  # CEC_USER_CONTROL_CODE_UP
        0x02: ButtonNames.DOWN,  # CEC_USER_CONTROL_CODE_DOWN
        0x03: ButtonNames.LEFT,  # CEC_USER_CONTROL_CODE_LEFT
        0x04: ButtonNames.RIGHT,  # CEC_USER_CONTROL_CODE_RIGHT
        0x30: ButtonNames.CHANNEL_UP,  # CEC_USER_CONTROL_CODE_CHANNEL_UP
        0x31: ButtonNames.CHANNEL_DOWN,  # CEC_USER_CONTROL_CODE_CHANNEL_DOWN
        0x32: ButtonNames.BACK,  # CEC_USER_CONTROL_CODE_PREVIOUS_CHANNEL
        # we will ignore volume as the TV itself can handle that
    }

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger('hdmicec_remote')

    def run_forever(self):
        with subprocess.Popen(
                [str(shutil.which("cec-client")), "-d", "31", "-t", "t"], stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
        ) as cec_client:
            for line in cec_client.stdout:
                match = self.key_up_regex.search(line)
                if match:
                    keycode = int(match.groups()[0], 16)
                    duration = int(match.groups()[1])
                    self._logger.debug(f"Key Pressed: {hex(keycode)}, duration: {duration}")
                    if duration > 25:
                        button_name = self._button_to_function.get(keycode, None)
                        if button_name:
                            self.button_callback(button_name)
                    continue
                match = self.power_up_regex.search(line)
                if match:
                    self._logger.debug(f"Display power-up detected.")
                    self.button_callback(ButtonNames.POWER_UP)
                    continue
                match = self.power_up_regex_alternate.search(line)
                if match:
                    self._logger.debug(f"Display power-up detected.")
                    self.button_callback(ButtonNames.POWER_UP)
                    continue
                match = self.power_off_regex.search(line)
                if match:
                    self._logger.debug(f"Display power-down detected.")
                    self.button_callback(ButtonNames.POWER_DOWN)
                    continue


class _FieldStationApi:
    """A simple wrapper around API calls, to be faked for ease in testing."""

    @staticmethod
    def load_api_key():
        if os.getenv('FS42_API_KEY'):
            return os.getenv('FS42_API_KEY')
        main_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'confs', 'main_config.json')
        try:
            with open(main_config) as f:
                key = json.load(f).get('api_key')
                return key.strip() if isinstance(key, str) and key.strip() else None
        except (OSError, ValueError, AttributeError):
            return None

    def __init__(self):
        # Server Configuration - can be overridden by environment variables
        self.FS42_HOST = os.getenv('FS42_HOST', '127.0.0.1')
        self.FS42_PORT = os.getenv('FS42_PORT', '4242')
        self.FS42_BASE_URL = f"http://{self.FS42_HOST}:{self.FS42_PORT}"

        self.FS42_API_KEY = self.load_api_key()

        self.api = requests.Session()
        if self.FS42_API_KEY:
            self.api.headers['X-API-Key'] = self.FS42_API_KEY
        self._logger = logging.getLogger('remote_control_api')

    def goto_channel(self, dest) -> bool:
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/channels/{dest}', "get",
            f"change_channel: {dest}")

    def get_status(self) -> Dict | None:
        try:
            response = self.api.get(f'{self.FS42_BASE_URL}/player/status')
            if response.ok:
                self._logger.debug(f"get_status succeeded.")
                return response.json()
            else:
                self._logger.debug(f"get_status command failed: ({response.status_code})")
        except Exception as e:
            self._logger.debug(f"API command error for get_status: {e}")
        return None

    def power(self, start_or_stop) -> bool:
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/manage/{start_or_stop}', "post",
            f"change_power: {start_or_stop}")

    def volume(self, change: str):
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/volume/change', "get",
            f"volume: {change}")

    def show_guide(self) -> bool:
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/channels/guide', "post",
            f"show_guide")

    def post_parental_pin(self, number) -> bool:
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/parental/digit/{number}', "post",
            f"parental_pin: {number}",
            timeout=2)

    def mpv_command_pressed(self, action) -> bool:
        """Send a non-interrupting mpv runtime command to FS42."""
        endpoint = action.replace("_", "-")
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/mpv/{endpoint}', "post",
            f"mpv: {action}",
            timeout=2)

    def navigate(self, direction) -> bool:
        return self._try_api_call(
            f'{self.FS42_BASE_URL}/player/web/key/{direction}', "post",
            f"navigate: {direction}",
            timeout=2)

    def _try_api_call(self, url: str, method: str, action_name: str, timeout=None) -> bool:
        try:
            response = self.api.request(method,
                                        url,
                                        timeout=timeout,
                                        )

            if response.ok:
                self._logger.debug(f"API command sent: {action_name}")
                return True
            else:
                self._logger.debug(f"API command failed: {action_name} ({response.status_code})")
        except Exception as e:
            self._logger.debug(f"API command error for {action_name}: {e}")
        return False


class _NumberTimer:
    """A wrapper around threading.Timer allowing for ease in testing."""

    def __init__(self):
        self.on_complete = None
        self._timeout: threading.Timer | None = None

    def start(self, duration: float):
        existing = self._timeout
        if existing:
            existing.cancel()
        timer = threading.Timer(duration, self._timer_finished)
        timer.start()
        self._timeout = timer

    def _timer_finished(self):
        self._timeout = None
        self.on_complete()

    def is_waiting(self):
        timer = self._timeout
        return False if not timer else not timer.finished

    def complete_early(self):
        timer = self._timeout
        if timer:
            timer.cancel()
            self.on_complete()
        self._timeout = None

    def wait_for_status(self):
        time.sleep(0.05)


class RemoteControl:
    def __init__(self, remote: BaseRemote, fsapi: _FieldStationApi, timer: _NumberTimer):
        self._logger = logging.getLogger("cec-remote")
        # Last channel tracking
        self.current_channel = None
        self.last_channel = None
        self.api = fsapi
        self._timer = timer
        self._timer.on_complete = self.handle_channel_number

        remote.button_callback = self.handle_button

        self.number_buffer = []

    def send_parental_digit_if_active(self, number):
        try:
            status = self.api.get_status()
            if not status:
                return False
            if not status.get("awaiting_pin"):
                return False

            return self.api.post_parental_pin(number)
        except Exception as ex:
            self._logger.error(f"Parental controls digit error: {ex}")
            return False

    def number_pressed(self, number) -> bool:
        """Handle number key presses from remote"""

        if self.send_parental_digit_if_active(number):
            return False

        self.number_buffer.append(number)
        if len(self.number_buffer) >= 3:
            self._timer.complete_early()
        else:
            self._timer.start(1.0)
        return True

    def nav_key_pressed(self, key_name) -> bool:
        """Forward a navigation key to the web channel (PPV, interactive guide) through the server"""
        return self.api.navigate(key_name)

    def show_guide(self) -> bool:
        """Handle home key press"""
        return self.api.show_guide()

    def change_channel(self, dest) -> bool:
        try:
            if dest == 'last':
                if self.last_channel:
                    dest = self.last_channel
                else:
                    return False
            response = self.api.goto_channel(dest)
            if response:
                # self._logger.debug(f"Channel changed success: {dest}")
                # Poll status to wait for channel change (max 1 second)
                try:
                    old_channel = self.current_channel
                    new_channel = None
                    max_attempts = 20  # 20 attempts * 0.05s = 1 second max

                    for attempt in range(max_attempts):
                        self._timer.wait_for_status()
                        status = self.api.get_status()
                        if status:
                            new_channel = status.get('channel_number')
                            # If channel changed or we have a channel number, we're done
                            if new_channel != old_channel:
                                break

                    self._logger.debug(
                        f"status returned channel_number={new_channel}, current_channel={self.current_channel}")
                    # Only update last_channel if the channel actually changed
                    if new_channel != self.current_channel and self.current_channel is not None:
                        self.last_channel = self.current_channel
                        self._logger.debug(
                            f"Channel changed: {self.current_channel} -> {new_channel} (Last: {self.last_channel})")
                    else:
                        self._logger.debug(f"Channel unchanged: new={new_channel}, current={self.current_channel}")
                    self.current_channel = new_channel
                    return True
                except Exception as e:
                    self._logger.debug(f"Failed to get current channel: {e}")
                    self.current_channel = None
            else:
                self._logger.warning(f"Channel {dest} failed")
        except Exception as e:
            self._logger.error(f"Channel {dest} error: {e}")
        return False

    def handle_channel_number(self):
        channel_number = "".join([str(i) for i in self.number_buffer])
        self.number_buffer = []
        self.change_channel(channel_number)

    def handle_power(self, on_off) -> bool:
        if on_off == "toggle":
            return False  # TODO I'll get to it
        return self.api.power(on_off)

    POWER_HANDLING = {ButtonNames.POWER_DOWN: "stop",
                      ButtonNames.POWER_UP: "start",
                      ButtonNames.POWER_TOGGLE: "toggle"}
    VOLUME = {ButtonNames.VOLUME_DOWN: "down",
              ButtonNames.VOLUME_UP: "up",
              ButtonNames.MUTE: "mute"}
    CHANNEL_CHANGING = {ButtonNames.CHANNEL_DOWN: "down",
                        ButtonNames.CHANNEL_UP: "up",
                        ButtonNames.BACK: "last"}
    NAVIGATION = {ButtonNames.UP: "PageUp",
                  ButtonNames.DOWN: "PageDown",
                  ButtonNames.LEFT: "NavLeft",
                  ButtonNames.RIGHT: "NavRight",
                  ButtonNames.ENTER: "Enter"}
    MPV_FUNCTIONS = {ButtonNames.CYCLE_SUBTITLES: "cycle_subtitles",
                     ButtonNames.TOGGLE_SUBTITLES: "toggle_subtitles",
                     ButtonNames.CYCLE_AUDIO: "cycle_audio", }

    def handle_button(self, button_name: str) -> bool:
        if button_name in self.POWER_HANDLING:
            return self.handle_power(self.POWER_HANDLING[button_name])
        if button_name in self.VOLUME:
            return self.api.volume(self.VOLUME[button_name])
        if button_name in self.CHANNEL_CHANGING:
            return self.change_channel(self.CHANNEL_CHANGING[button_name])
        if button_name in self.NAVIGATION:
            return self.nav_key_pressed(self.NAVIGATION[button_name])
        if button_name in self.MPV_FUNCTIONS:
            return self.api.mpv_command_pressed(self.MPV_FUNCTIONS[button_name])
        if button_name == ButtonNames.GUIDE:
            return self.show_guide()

        if button_name.startswith(ButtonNames.NUMBER_PREFIX):
            number_only = button_name.replace(ButtonNames.NUMBER_PREFIX, '')
            return self.number_pressed(number_only)
        return False


def find_input_device(device_spec: str | None = None):
    """Find the Flirc or keyboard input device

    Args:
        device_spec: Optional device specifier. Can be:
            - Device path (e.g., '/dev/input/event3')
            - Device index (e.g., '0', '1', '2')
            - Device name pattern (e.g., 'flirc', 'keyboard')
            - None to auto-detect
    """

    devices = []
    default = False
    # Look for input devices
    devs = glob.glob("/dev/input/event*")
    print(devs)
    for device_path in glob.glob('/dev/input/event*'):
        try:
            device = InputDevice(device_path)
            print(f"{device_path}: {device.name}, {device.capabilities()}")
            # Look for devices that can send key events
            if ecodes.EV_KEY in device.capabilities():
                devices.append((device_path, device.name))
        except (OSError, PermissionError):
            continue

    if not devices:
        print("No keyboard/remote devices found. Run with sudo?")
        return None

    print("Available input devices:")
    for i, (path, name) in enumerate(devices):
        print(f"{i}: {name} ({path})")

    # If device_spec is provided, try to match it
    if device_spec:
        # Check if it's a direct device path
        if device_spec.startswith('/dev/input/'):
            if os.path.exists(device_spec):
                print(f"Using specified device path: {device_spec}")
                return device_spec
            else:
                print(f"Warning: Device path '{device_spec}' not found, falling back to auto-detect")

        # Check if it's a numeric index
        elif device_spec.isdigit():
            index = int(device_spec)
            if 0 <= index < len(devices):
                path, name = devices[index]
                print(f"Using device at index {index}: {name} ({path})")
                return path
            else:
                print(
                    f"Warning: Device index {index} out of range (0-{len(devices) - 1}), falling back to auto-detect")

        # Treat it as a name pattern
        else:
            device_spec = device_spec.lower()

    # If no spec provided, default to flirc
    if not device_spec:
        device_spec = "flirc"
        default = True

    # Try to match requested device
    for path, name in devices:
        if device_spec.lower() in name.lower():
            print(f"Found device: {name}")
            return path

    # If user explicitly requested device, do NOT fallback
    if default is False and (device_spec or os.getenv('FS42_INPUT_DEVICE')):
        print(f"Device '{device_spec}' not found yet. Waiting...")
        return None

    # Otherwise fallback to first keyboard device
    print(f"Using default device: {devices[0][1]}")
    return devices[0][0]


SETTINGS_FILE = "runtime/remote_controller.json"


def load_settings() -> Dict:
    if os.path.exists(SETTINGS_FILE):
        print(f"Loading settings from {SETTINGS_FILE}")
        try:
            with open(SETTINGS_FILE, 'r') as file:
                remote_settings = json.load(file)
            if remote_settings.get("key_mappings") is not None:
                print("Loading KEY_MAPPINGS from file")
                return remote_settings["key_mappings"]
        except Exception as e:
            print(f"Error loading settings from file: {e}")
    return {}


def main(base_remote: BaseRemote,
         api: _FieldStationApi,
         timer: _NumberTimer = _NumberTimer()):
    remote = RemoteControl(base_remote, api, timer)
    base_remote.run_forever()
    return remote


if __name__ == "__main__":
    """Main function to start the input device listener"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='FieldStation42 Remote Controller',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Device specification examples:
  -d /dev/input/event3      Use specific device path
  -d 0                      Use device at index 0 from the device list
  -d flirc                  Use first device with 'flirc' in its name
  -d keyboard               Use first device with 'keyboard' in its name
  -d test                   Run test mode
  -d hdmi                   Use HDMI-CEC to receive messages from TV.
  -d all                    Listen to all keyboard/remote input devices

Environment variables:
  FS42_INPUT_DEVICE         Device specification (same format as -d)
  FS42_HOST                 Server host (default: 127.0.0.1)
  FS42_PORT                 Server port (default: 4242)
  FS42_API_KEY              API key (default: api_key from confs/main_config.json)
        """
    )
    parser.add_argument(
        '-d', '--device',
        help='Input device to use (path, index, name pattern, "all", or "test")',
        default=None
    )
    parser.add_argument(
        '--list-devices',
        action='store_true',
        help='List available input devices and exit'
    )

    args = parser.parse_args()

    # Get device spec from args or environment variable
    device_spec = args.device or os.getenv('FS42_INPUT_DEVICE')

    fs_api = _FieldStationApi()
    print(f"Remote Controller started. Connecting to {fs_api.FS42_BASE_URL}")

    # If --list-devices, just show devices and exit
    if args.list_devices:
        find_input_device(device_spec)
        exit(0)

    run_once = False
    if device_spec == "all":
        logging.info("Using all keyboard/remote input devices")
        device_path = "all"
    # Find single input device
    elif device_spec == "test":
        device_path = "test"
        run_once = True
    elif device_spec == "hdmi":
        device_path = "hdmi"
        run_once = True
    else:
        device_path = find_input_device(device_spec)

    print("Press ESC to exit.")

    first_run = True
    while True:
        try:
            if device_path == "all":
                remote_input = FlircRemoteAllDevices(load_settings())
            elif device_path == "hdmi":
                remote_input = HdmiCecRemote()
            elif device_path == "test":
                remote_input = TestModeRemote()
            else:
                if not device_path:
                    print("Selected input not found. Retrying in 5 seconds...")
                    time.sleep(5)
                    # Check if the device has reconnected
                    device_path = find_input_device(device_spec)

                    if not device_path:
                        continue

                device = InputDevice(device_path)
                print(f"Listening for remote control commands from: {device.name}")
                remote_input = FlircRemote(device, load_settings())

            # Main event loop
            main(remote_input, fs_api)

        except FileNotFoundError:
            print("Input device missing. Waiting for reconnection...")
            time.sleep(5)

        except PermissionError:
            print("Permission denied. Try running with: sudo python3 remote_controller.py")
            sys.exit(1)

        except OSError as e:
            # Bluetooth disconnect / USB unplug / device vanished
            if e.errno == 19 or e.errno == 2:
                print("Input device disconnected. Waiting for reconnection...")
                time.sleep(5)
            else:
                print(f"Device error: {e}")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\nExiting remote controller...")
            sys.exit(1)

        except Exception as ex:
            print(f"Error: {ex}")
            sys.exit(1)

        if run_once:
            sys.exit(0)
