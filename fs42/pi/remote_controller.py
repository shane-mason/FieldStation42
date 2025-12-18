#!/usr/bin/env python3

from evdev import InputDevice, ecodes
import requests
import os
import subprocess
import threading
import sys
import time


# ======================================
# CONFIGURATION - CUSTOMIZE YOUR MAPPINGS
# ======================================

# Server Configuration - can be overridden by environment variables
FS42_HOST = os.getenv('FS42_HOST', '127.0.0.1')
FS42_PORT = os.getenv('FS42_PORT', '4242')
FS42_BASE_URL = f"http://{FS42_HOST}:{FS42_PORT}"

# Debounce Configuration - Time in seconds to wait between repeated button presses
DEBOUNCE_TIME = 0.25  # 250ms default debounce time

# Services to toggle when power button is pressed (remote-controller is never toggled)
SERVICES_TO_TOGGLE = [
    'fs42.service',           # Field Player
    'fs42-cable-box.service', # Cable Box
    'fs42-osd.service',       # On-Screen Display
]

# Key Mappings - Change these to customize which keys do what
# Available key names: 'home', 'end', 'up', 'down', 'left', 'right', 'space', 'enter',
# 'esc', 'tab', 'backspace', 'delete', 'insert', 'pageup', 'pagedown', 'f1'-'f12',
# 'a'-'z', 'leftshift', 'rightshift', 'leftctrl', 'rightctrl', 'leftalt', 'rightalt'
KEY_MAPPINGS = {
    # Remote control functions
    'show_guide': 'home',        # Show program guide
    'volume_up': 'right',        # Increase volume
    'volume_down': 'left',       # Decrease volume
    'channel_up': 'up',          # Next channel
    'channel_down': 'down',      # Previous channel
    'last_channel': 'backspace', # Switch to last channel
    'mute': 'm',                 # Mute/unmute volume
    'power_stop': 'end',         # Stop player (power button)
    'exit': 'esc',               # Exit remote controller

    # Alternative mappings (uncomment to use):
    # 'power_stop': 'space',     # Use spacebar for power/stop
    # 'show_guide': 'g',         # Use 'g' key for guide
    # 'volume_up': 'pageup',     # Use page up for volume up
    # 'volume_down': 'pagedown', # Use page down for volume down
}

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


def send_channel_change():
    """Send accumulated channel input to the server"""
    global channel_input, channel_input_timer, current_channel, last_channel
    
    with input_lock:
        if channel_input:
            try:
                channel_number = int(channel_input)
                print(f"Sending channel change to {channel_number}")
                response = requests.get(f'{FS42_BASE_URL}/player/channels/{channel_number}')
                if response.ok:
                    print(f"Changed to channel {channel_number}")
                    # Update channel tracking - only update last_channel if we know the current channel
                    if current_channel is not None and current_channel != channel_number:
                        last_channel = current_channel
                        print(f"Updated last_channel: {last_channel} (was on {current_channel}, now on {channel_number})")
                    current_channel = channel_number
                else:
                    print(f"Channel change to {channel_number} failed")
            except Exception as e:
                print(f"Channel change error: {e}")
            
            # Clear the input
            channel_input = ''
            channel_input_timer = None


def number_pressed(number):
    """Handle number key presses from remote"""
    global channel_input, channel_input_timer
    
    with input_lock:
        # Cancel any existing timer
        if channel_input_timer:
            channel_input_timer.cancel()
            channel_input_timer = None
        
        # Add digit to input
        channel_input += str(number)
        print(f"Channel input: {channel_input}")
        
        # If we have 3 digits, send immediately
        if len(channel_input) >= 3:
            # Use a very short timer to avoid race conditions
            channel_input_timer = threading.Timer(0.1, send_channel_change)
            channel_input_timer.start()
        else:
            # Set timeout for 1 second
            channel_input_timer = threading.Timer(1.0, send_channel_change)
            channel_input_timer.start()


def show_guide_pressed():
    """Handle home key press"""
    if not should_allow_press('show_guide'):
        return  # Debounced - ignore this press

    try:
        response = requests.post(f'{FS42_BASE_URL}/player/channels/guide')
        if response.ok:
            print("Guide displayed")
        else:
            print("Guide command failed")
    except Exception as e:
        print(f"Guide error: {e}")


def volume_up_pressed():
    """Handle right arrow key press"""
    if not should_allow_press('volume_up'):
        return  # Debounced - ignore this press

    try:
        response = requests.get(f'{FS42_BASE_URL}/player/volume/up')
        if response.ok:
            data = response.json()
            print(f"Volume up: {data.get('volume', 'success')}")
        else:
            print("Volume up failed")
    except Exception as e:
        print(f"Volume up error: {e}")


def volume_down_pressed():
    """Handle left arrow key press"""
    if not should_allow_press('volume_down'):
        return  # Debounced - ignore this press

    try:
        response = requests.get(f'{FS42_BASE_URL}/player/volume/down')
        if response.ok:
            data = response.json()
            print(f"Volume down: {data.get('volume', 'success')}")
        else:
            print("Volume down failed")
    except Exception as e:
        print(f"Volume down error: {e}")


def mute_pressed():
    """Handle mute key press"""
    if not should_allow_press('mute'):
        return  # Debounced - ignore this press

    try:
        response = requests.get(f'{FS42_BASE_URL}/player/volume/mute')
        if response.ok:
            data = response.json()
            print(f"Mute toggled: {data.get('volume', 'success')}")
        else:
            print("Mute toggle failed")
    except Exception as e:
        print(f"Mute error: {e}")


def channel_up_pressed():
    """Handle up arrow key press"""
    if not should_allow_press('channel_up'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = requests.get(f'{FS42_BASE_URL}/player/channels/up')
        if response.ok:
            print("Channel up success")
            # Poll status to wait for channel change (max 1 second)
            try:
                old_channel = current_channel
                new_channel = None
                max_attempts = 20  # 20 attempts * 0.05s = 1 second max

                for attempt in range(max_attempts):
                    time.sleep(0.05)
                    status_response = requests.get(f'{FS42_BASE_URL}/player/status')
                    if status_response.ok:
                        status = status_response.json()
                        new_channel = status.get('channel_number')

                        # If channel changed or we have a channel number, we're done
                        if new_channel != old_channel:
                            break

                print(f"DEBUG: Status returned channel_number={new_channel}, current_channel={current_channel}")
                # Only update last_channel if the channel actually changed
                if new_channel != current_channel and current_channel is not None:
                    last_channel = current_channel
                    print(f"Channel changed: {current_channel} -> {new_channel} (Last: {last_channel})")
                else:
                    print(f"Channel unchanged: new={new_channel}, current={current_channel}")
                current_channel = new_channel
            except Exception as e:
                print(f"Failed to get current channel: {e}")
                current_channel = None
        else:
            print("Channel up failed")
    except Exception as e:
        print(f"Channel up error: {e}")


def channel_down_pressed():
    """Handle down arrow key press"""
    if not should_allow_press('channel_down'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = requests.get(f'{FS42_BASE_URL}/player/channels/down')
        if response.ok:
            print("Channel down success")
            # Poll status to wait for channel change (max 1 second)
            try:
                old_channel = current_channel
                new_channel = None
                max_attempts = 20  # 20 attempts * 0.05s = 1 second max

                for attempt in range(max_attempts):
                    time.sleep(0.05)
                    status_response = requests.get(f'{FS42_BASE_URL}/player/status')
                    if status_response.ok:
                        status = status_response.json()
                        new_channel = status.get('channel_number')

                        # If channel changed or we have a channel number, we're done
                        if new_channel != old_channel:
                            break

                print(f"DEBUG: Status returned channel_number={new_channel}, current_channel={current_channel}")
                # Only update last_channel if the channel actually changed
                if new_channel != current_channel and current_channel is not None:
                    last_channel = current_channel
                    print(f"Channel changed: {current_channel} -> {new_channel} (Last: {last_channel})")
                else:
                    print(f"Channel unchanged: new={new_channel}, current={current_channel}")
                current_channel = new_channel
            except Exception as e:
                print(f"Failed to get current channel: {e}")
                current_channel = None
        else:
            print("Channel down failed")
    except Exception as e:
        print(f"Channel down error: {e}")


def last_channel_pressed():
    """Handle last channel key press"""
    if not should_allow_press('last_channel'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    if last_channel is not None:
        try:
            print(f"Switching to last channel: {last_channel}")
            response = requests.get(f'{FS42_BASE_URL}/player/channels/{last_channel}')
            if response.ok:
                print(f"Switched to last channel {last_channel}")
                # Swap current and last channel
                temp = current_channel
                current_channel = last_channel
                last_channel = temp
            else:
                print(f"Last channel change to {last_channel} failed")
        except Exception as e:
            print(f"Last channel error: {e}")
    else:
        print("No last channel stored")


def end_pressed():
    """Handle end key press - stop the player"""
    if not should_allow_press('power_stop'):
        return  # Debounced - ignore this press

    try:
        response = requests.get(f'{FS42_BASE_URL}/player/commands/stop')
        if response.ok:
            print("Player stopped")
        else:
            print("Stop command failed")
    except Exception as e:
        print(f"Stop error: {e}")


def toggle_services():
    """Toggle FieldStation42 services on/off - true power button behavior"""
    if not should_allow_press('power_stop'):
        return  # Debounced - ignore this press

    try:
        # Check if fs42.service is active to determine current state
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', 'fs42.service'],
            capture_output=True,
            text=True,
            timeout=5
        )

        services_active = result.stdout.strip() == 'active'

        if services_active:
            # Services are running, stop them
            for service in SERVICES_TO_TOGGLE:
                try:
                    subprocess.run(
                        ['systemctl', '--user', 'stop', service],
                        capture_output=True,
                        timeout=10
                    )
                    print(f"Stopped {service}")
                except Exception as e:
                    print(f"Error stopping {service}: {e}")
        else:
            # Services are not running, start them
            for service in SERVICES_TO_TOGGLE:
                try:
                    subprocess.run(
                        ['systemctl', '--user', 'start', service],
                        capture_output=True,
                        timeout=10
                    )
                    print(f"Started {service}")
                except Exception as e:
                    print(f"Error starting {service}: {e}")

    except subprocess.TimeoutExpired:
        print("Error: systemctl command timed out")
    except Exception as e:
        print(f"Error toggling services: {e}")


def find_input_device():
    """Find the Flirc or keyboard input device"""
    import glob
    devices = []
    
    # Look for input devices
    for device_path in glob.glob('/dev/input/event*'):
        try:
            device = InputDevice(device_path)
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
    
    # Try to find Flirc first
    for path, name in devices:
        if 'flirc' in name.lower():
            print(f"Found Flirc device: {name}")
            return path
    
    # Use first keyboard-like device
    return devices[0][0]


def get_key_name_from_code(key_code):
    """Convert evdev key code to readable key name"""
    key_map = {
        ecodes.KEY_HOME: 'home', ecodes.KEY_END: 'end',
        ecodes.KEY_UP: 'up', ecodes.KEY_DOWN: 'down',
        ecodes.KEY_LEFT: 'left', ecodes.KEY_RIGHT: 'right',
        ecodes.KEY_SPACE: 'space', ecodes.KEY_ENTER: 'enter',
        ecodes.KEY_ESC: 'esc', ecodes.KEY_TAB: 'tab',
        ecodes.KEY_BACKSPACE: 'backspace', ecodes.KEY_DELETE: 'delete',
        ecodes.KEY_INSERT: 'insert', ecodes.KEY_PAGEUP: 'pageup',
        ecodes.KEY_PAGEDOWN: 'pagedown',
        ecodes.KEY_F1: 'f1', ecodes.KEY_F2: 'f2', ecodes.KEY_F3: 'f3',
        ecodes.KEY_F4: 'f4', ecodes.KEY_F5: 'f5', ecodes.KEY_F6: 'f6',
        ecodes.KEY_F7: 'f7', ecodes.KEY_F8: 'f8', ecodes.KEY_F9: 'f9',
        ecodes.KEY_F10: 'f10', ecodes.KEY_F11: 'f11', ecodes.KEY_F12: 'f12',
        ecodes.KEY_LEFTSHIFT: 'leftshift', ecodes.KEY_RIGHTSHIFT: 'rightshift',
        ecodes.KEY_LEFTCTRL: 'leftctrl', ecodes.KEY_RIGHTCTRL: 'rightctrl',
        ecodes.KEY_LEFTALT: 'leftalt', ecodes.KEY_RIGHTALT: 'rightalt',
    }

    # Add letter keys a-z using ecodes constants
    key_map[ecodes.KEY_A] = 'a'
    key_map[ecodes.KEY_B] = 'b'
    key_map[ecodes.KEY_C] = 'c'
    key_map[ecodes.KEY_D] = 'd'
    key_map[ecodes.KEY_E] = 'e'
    key_map[ecodes.KEY_F] = 'f'
    key_map[ecodes.KEY_G] = 'g'
    key_map[ecodes.KEY_H] = 'h'
    key_map[ecodes.KEY_I] = 'i'
    key_map[ecodes.KEY_J] = 'j'
    key_map[ecodes.KEY_K] = 'k'
    key_map[ecodes.KEY_L] = 'l'
    key_map[ecodes.KEY_M] = 'm'
    key_map[ecodes.KEY_N] = 'n'
    key_map[ecodes.KEY_O] = 'o'
    key_map[ecodes.KEY_P] = 'p'
    key_map[ecodes.KEY_Q] = 'q'
    key_map[ecodes.KEY_R] = 'r'
    key_map[ecodes.KEY_S] = 's'
    key_map[ecodes.KEY_T] = 't'
    key_map[ecodes.KEY_U] = 'u'
    key_map[ecodes.KEY_V] = 'v'
    key_map[ecodes.KEY_W] = 'w'
    key_map[ecodes.KEY_X] = 'x'
    key_map[ecodes.KEY_Y] = 'y'
    key_map[ecodes.KEY_Z] = 'z'
    
    return key_map.get(key_code)


def handle_key_event(event):
    """Handle key press events from evdev"""
    if event.type == ecodes.EV_KEY and event.value == 1:  # Key press (not release)
        key_code = event.code

        # Number keys (1-9, 0) - always handled the same way
        if key_code >= ecodes.KEY_1 and key_code <= ecodes.KEY_9:
            number = key_code - ecodes.KEY_1 + 1
            number_pressed(number)
            return True
        elif key_code == ecodes.KEY_0:
            number_pressed(0)
            return True

        # Get the key name and check if it's mapped to a function
        key_name = get_key_name_from_code(key_code)
        if not key_name:
            print(f"DEBUG: Unknown key code: {key_code}")
            return True

        print(f"DEBUG: Key pressed: {key_name} (code: {key_code})")

        # Check mappings and call appropriate function
        for function_name, mapped_key in KEY_MAPPINGS.items():
            if key_name == mapped_key:
                print(f"DEBUG: Matched function: {function_name}")
                if function_name == 'show_guide':
                    show_guide_pressed()
                elif function_name == 'volume_up':
                    volume_up_pressed()
                elif function_name == 'volume_down':
                    volume_down_pressed()
                elif function_name == 'mute':
                    mute_pressed()
                elif function_name == 'channel_up':
                    channel_up_pressed()
                elif function_name == 'channel_down':
                    channel_down_pressed()
                elif function_name == 'last_channel':
                    last_channel_pressed()
                elif function_name == 'power_stop':
                    #end_pressed()
                    toggle_services()
                elif function_name == 'exit':
                    print("Exiting remote controller...")
                    return False
                break

    return True


def main():
    """Main function to start the input device listener"""
    print(f"Remote Controller started. Connecting to {FS42_BASE_URL}")
    print("Press ESC to exit.")
    
    # Find input device
    device_path = find_input_device()
    if not device_path:
        sys.exit(1)
    
    try:
        device = InputDevice(device_path)
        print(f"Listening for remote control commands from: {device.name}")
        
        # Read events from the device
        for event in device.read_loop():
            if not handle_key_event(event):
                break
                
    except PermissionError:
        print("Permission denied. Try running with: sudo python3 remote_controller.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting remote controller...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()