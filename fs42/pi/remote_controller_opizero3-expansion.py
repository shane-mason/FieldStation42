#!/usr/bin/env python3
import requests
import subprocess
import threading
import json
import time
import evdev
import glob
import os
from evdev import InputDevice, ecodes

IR_DEVICE_NAME = "sunxi-ir"          # exact name reported by the kernel driver
BY_PATH_HINT = "platform-7040000.ir"  # substring of the stable /dev/input/by-path/ symlink

# ======================================
# CONFIGURATION - CUSTOMIZE YOUR MAPPINGS
# ======================================

# Server Configuration - can be overridden by environment variables
FS42_HOST = os.getenv('FS42_HOST', '127.0.0.1')
FS42_PORT = os.getenv('FS42_PORT', '4242')
FS42_BASE_URL = f"http://{FS42_HOST}:{FS42_PORT}"

# Fill this in once you've logged your remote's actual codes
# Scancodes are from Dévant EN2H27D
BUTTON_MAP = {
    0x408: "POWER_MAIN",
    0x40b: "SOURCE_BTN",
    0x410: "NUM_0",
    0x411: "NUM_1",
    0x412: "NUM_2",
    0x413: "NUM_3",
    0x414: "NUM_4",
    0x415: "NUM_5",
    0x416: "NUM_6",
    0x417: "NUM_7",
    0x418: "NUM_8",
    0x419: "NUM_9",
    0x440: "EPG_BTN",
    0x450: "CC_BTN",
    0x402: "VOLUME_UP",
    0x403: "VOLUME_DOWN",
    0x400: "CH_UP",
    0x401: "CH_DOWN"
}

PRESS_SOCKET = "runtime/press.socket"

def _stable_path_for(event_path):
    """
    Prefer a /dev/input/by-path/ symlink over the raw eventN path, since
    eventN numbering isn't guaranteed to stay the same across reboots
    once other input devices (USB keyboard, HDMI-CEC, etc.) get added.
    Falls back to the raw path if no matching symlink is found.
    """
    by_path_dir = "/dev/input/by-path/"
    if not os.path.isdir(by_path_dir):
        return event_path
    try:
        real_target = os.path.realpath(event_path)
        for link_name in os.listdir(by_path_dir):
            link_path = os.path.join(by_path_dir, link_name)
            if os.path.realpath(link_path) == real_target and BY_PATH_HINT in link_name:
                return link_path
    except OSError:
        pass
    return event_path


def find_input_device(device_spec=None):
    """
    Find the Orange Pi Zero 3's onboard IR receiver (sunxi-ir).

    Args:
        device_spec: Optional override. Can be:
            - Device path (e.g. '/dev/input/event3' or a by-path symlink)
            - Device index (e.g. '0', '1', '2') from the printed list
            - Device name pattern (e.g. 'sunxi-ir', 'ir')
            - None to auto-detect the sunxi-ir device specifically

    Returns:
        A stable device path string, or None if not found.
    """
    candidates = []  # (path, name, has_ev_key, has_ev_msc)

    for event_path in sorted(glob.glob("/dev/input/event*")):
        try:
            device = InputDevice(event_path)
        except (OSError, PermissionError):
            continue

        caps = device.capabilities()
        has_ev_key = ecodes.EV_KEY in caps
        has_ev_msc = ecodes.EV_MSC in caps

        # We only care about devices that could plausibly be a remote:
        # either real key events (keymap loaded) or raw IR scancodes.
        if has_ev_key or has_ev_msc:
            candidates.append((event_path, device.name, has_ev_key, has_ev_msc))

    if not candidates:
        print("No IR/keyboard-capable input devices found at all.")
        print("Checklist:")
        print("  1. Is the 'ir' overlay enabled? Check /boot/armbianEnv.txt for 'overlays=ir'")
        print("  2. Did it load? Run: dmesg | grep -i sunxi-ir")
        print("  3. Are you running with enough permissions? Try with sudo, or add")
        print("     your user to the 'input' group.")
        return None

    print("Available input devices:")
    for i, (path, name, has_key, has_msc) in enumerate(candidates):
        mode = []
        if has_key:
            mode.append("EV_KEY")
        if has_msc:
            mode.append("EV_MSC/scancode")
        print(f"  {i}: {name} ({path}) [{', '.join(mode)}]")

    # --- Explicit override handling -------------------------------------
    if device_spec:
        if device_spec.startswith("/dev/input/"):
            if os.path.exists(device_spec):
                print(f"Using specified device path: {device_spec}")
                return device_spec
            print(f"Warning: '{device_spec}' not found, falling back to auto-detect")

        elif device_spec.isdigit():
            index = int(device_spec)
            if 0 <= index < len(candidates):
                path, name, *_ = candidates[index]
                print(f"Using device at index {index}: {name} ({path})")
                return _stable_path_for(path)
            print(f"Warning: index {index} out of range (0-{len(candidates)-1}), "
                  f"falling back to auto-detect")

        else:
            for path, name, *_ in candidates:
                if device_spec.lower() in name.lower():
                    print(f"Found device matching '{device_spec}': {name}")
                    return _stable_path_for(path)
            print(f"Device '{device_spec}' not found yet. Waiting...")
            return None

    # --- Default: look specifically for the sunxi-ir device -------------
    for path, name, has_key, has_msc in candidates:
        if IR_DEVICE_NAME.lower() in name.lower():
            resolved = _stable_path_for(path)
            print(f"Found sunxi-ir device: {name} ({resolved})")
            if not has_key:
                print("Note: no EV_KEY events — no keymap loaded yet.")
                print("Run 'ir-keytable -s rc0' to check, or load one with "
                      "'ir-keytable -w <file> -s rc0' if you want standard "
                      "key events instead of raw scancodes.")
            return resolved

    # --- sunxi-ir not present: don't silently grab an unrelated device --
    print(f"'{IR_DEVICE_NAME}' not found among input devices.")
    print("This usually means the 'ir' device tree overlay isn't enabled, or")
    print("the expansion board's IR receiver isn't wired/seated correctly.")
    print("Check: dmesg | grep -i sunxi-ir")
    return None

# How long (seconds) a scancode's repeat events are allowed to keep
# re-firing the same action while a button is held. Set to 0 to allow
# every single repeat through unthrottled.
REPEAT_HOLD_WINDOW = 0.4
# Minimum gap (seconds) after a repeat window ends before the SAME
# scancode can fire again as a fresh press (basic debounce).
DEBOUNCE_COOLDOWN = 0.25

# How long to wait between retries if the receiver isn't found yet
# (e.g. overlay not loaded, or script started before udev settles).
DEVICE_WAIT_RETRY_SECONDS = 5

# Channel input state
channel_input = ''
channel_input_timer = None
input_lock = threading.Lock()

# Last channel tracking
current_channel = None
last_channel = None

# Debounce tracking - stores last press time for each function
last_press_time = {}
debounce_lock = threading.Lock()

def write_press_socket(digits):
    try:
        with open(PRESS_SOCKET, "w") as fp:
            json.dump({"digits": digits, "ts": time.time()}, fp)
    except Exception as e:
        print(f"Failed to write press socket: {e}")


def clear_press_socket():
    try:
        with open(PRESS_SOCKET, "w") as fp:
            fp.write("")
    except Exception:
        pass


def should_allow_press(function_name, debounce_time=DEBOUNCE_TIME):
    """Check if enough time has passed since last press of this function"""
    global last_press_time

    with debounce_lock:
        current_time = time.time()
        last_time = last_press_time.get(function_name, 0)

        if current_time - last_time >= debounce_time:
            last_press_time[function_name] = current_time
            return True
        else:
            return False

def wait_for_device():
    """Block until find_input_device() locates the sunxi-ir receiver."""
    while True:
        path = find_input_device("sunxi-ir")
        if path:
            return path
        print(f"Retrying in {DEVICE_WAIT_RETRY_SECONDS}s...")
        time.sleep(DEVICE_WAIT_RETRY_SECONDS)

def should_allow_press(function_name, debounce_time=DEBOUNCE_TIME):
    """Check if enough time has passed since last press of this function"""
    global last_press_time

    with debounce_lock:
        current_time = time.time()
        last_time = last_press_time.get(function_name, 0)

        if current_time - last_time >= debounce_time:
            last_press_time[function_name] = current_time
            return True
        else:
            return False

def show_guide_pressed():
    """Handle home key press"""
    if not should_allow_press('show_guide'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = requests.post(f'{FS42_BASE_URL}/player/channels/guide')
        if response.ok:
            print("Guide displayed")
            if current_channel is not None:
                last_channel = current_channel
                print(f"Stored last_channel: {last_channel} before guide")
        else:
            print("Guide command failed")
    except Exception as e:
        print(f"Guide error: {e}")

def handle_action(action, code):
    """
    Replace this with the actual call into FieldStation42's channel/
    playback control (e.g. posting to its command socket/queue).
    Kept as a print for now since this is the "does this button work"
    stage.
    """
    if action == "EPG_BTN":
        show_guide_pressed()
    
    print(f"[{hex(code)}] -> {action}")


def listen(dev):
    print(f"Listening on {dev.name} ({dev.path}). Ctrl+C to stop.\n")

    last_code = None
    last_event_time = 0.0

    for event in dev.read_loop():
        if event.type != evdev.ecodes.EV_MSC or event.code != evdev.ecodes.MSC_SCAN:
            continue

        code = event.value
        now = time.monotonic()
        action = BUTTON_MAP.get(code)

        if action is None:
            print(f"[{hex(code)}] -> unmapped scancode")
            last_code = code
            last_event_time = now
            continue

        # First time we see this code since it went idle -> fresh press.
        # Repeats of the SAME code within REPEAT_HOLD_WINDOW are treated
        # as "still held" and re-fire the action (useful for volume/
        # channel scrubbing); anything after a gap is a debounced repeat
        # until DEBOUNCE_COOLDOWN has passed.
        is_repeat_of_same = (code == last_code) and (now - last_event_time <= REPEAT_HOLD_WINDOW)

        if is_repeat_of_same or now - last_event_time > DEBOUNCE_COOLDOWN:
            handle_action(action, code)

        last_code = code
        last_event_time = now

def main():
    device_path = wait_for_device()
    dev = evdev.InputDevice(device_path)
    try:
        listen(dev)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

