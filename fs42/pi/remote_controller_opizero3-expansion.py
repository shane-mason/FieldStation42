#!/usr/bin/env python3
import evdev

DEVICE_PATH = "/dev/input/event0"

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

def main():
    dev = evdev.InputDevice(DEVICE_PATH)
    print(f"Listening on {dev.name}. Ctrl+C to stop.\n")

    for event in dev.read_loop():
        if event.type == evdev.ecodes.EV_MSC and event.code == evdev.ecodes.MSC_SCAN:
            code = event.value
            action = BUTTON_MAP.get(code)
            if action:
                print(f"[{hex(code)}] -> {action} button works!")
            else:
                print(f"[{hex(code)}] -> unmapped scancode")

if __name__ == "__main__":
    main()
