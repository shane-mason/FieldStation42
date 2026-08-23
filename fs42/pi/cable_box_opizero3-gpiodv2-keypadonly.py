import json
import time

# Orange Pi gpiod (v2.x API)
import gpiod
from gpiod.line import Direction, Value, Bias

# TM1637
import tm1637


CHIP_PATH = "/dev/gpiochip0"

# TM1637:
# CLK = PH6 / line 230
# DIO = PC10 / line 74

# 4x3 keypad GPIO lines.
# Change these if your final physical wiring uses different pins.
KEYPAD_COLS = [70, 228, 72]       # C1, C2, C3
KEYPAD_ROWS = [73, 232, 71, 69]   # R1, R2, R3, R4

KEYPAD = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["*", "0", "#"],
]


class CableBox:
    def __init__(
        self,
        channel_socket="runtime/channel.socket",
        status_socket="runtime/play_status.socket",
        press_socket="runtime/press.socket"
    ):
        self.channel_socket = channel_socket
        self.status_socket = status_socket
        self.press_socket = press_socket

        # TM1637 display
        self.tm = tm1637.TM1637(CHIP_PATH, clk=230, dio=74)
        self.tm.brightness(0)
        self.tm.show("FS42")

        self.last_stat = ""

        # Matrix keypad:
        #
        # Rows are outputs. Normally HIGH.
        # Columns are inputs with internal pull-ups.
        row_settings = gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=Value.ACTIVE,
        )

        col_settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            bias=Bias.PULL_UP,
        )

        self.keypad_request = gpiod.request_lines(
            CHIP_PATH,
            consumer="fieldstation42-keypad",
            config={
                tuple(KEYPAD_ROWS): row_settings,
                tuple(KEYPAD_COLS): col_settings,
            },
        )

        # Used so holding a key doesn't generate presses repeatedly.
        self.last_key = None

        self.temp_mode = False
        self.last_button_time = time.monotonic()
        self.show_time = True
        self.time_format = "%H:%M"

    def check_status(self):
        new_stat = None

        with open(self.status_socket) as fp:
            as_str = fp.read()

        if as_str != self.last_stat:
            print(f"Status changed: {as_str}")
            self.last_stat = as_str

            try:
                new_stat = json.loads(as_str)
            except Exception:
                # Assume partial read and try again next time.
                print(f"Error decoding status: {as_str}")

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

    def send_command(self, command, channel=-1):
        as_obj = {
            "command": command,
            "channel": channel,
        }

        as_str = json.dumps(as_obj)

        print(f"Sending command: {as_str}")

        with open(self.channel_socket, "w") as fp:
            fp.write(as_str)

    def scan_keypad(self):
        pressed = None

        for row_index, row in enumerate(KEYPAD_ROWS):

            # Put every row HIGH first.
            self.keypad_request.set_values({
                offset: Value.ACTIVE
                for offset in KEYPAD_ROWS
            })

            # Pull only the row currently being scanned LOW.
            self.keypad_request.set_value(
                row,
                Value.INACTIVE
            )

            # Allow GPIO levels to settle.
            time.sleep(0.001)

            for col_index, col in enumerate(KEYPAD_COLS):

                if self.keypad_request.get_value(col) == Value.INACTIVE:
                    pressed = KEYPAD[row_index][col_index]
                    break

            if pressed is not None:
                break

        # Return all rows HIGH when we're finished scanning.
        self.keypad_request.set_values({
            offset: Value.ACTIVE
            for offset in KEYPAD_ROWS
        })

        return pressed

    def read_key(self):
        key = self.scan_keypad()

        # Key was released.
        if key is None:
            self.last_key = None
            return None

        # Same physical press is still being held.
        if key == self.last_key:
            return None

        # New key press.
        self.last_key = key
        print(f"Key pressed: {key}")

        return key

    def event_loop(self):
        in_selection = False
        selection_digits = ""
        last_selection_tick = -1

        channel_num = 0
        tick_count = 0

        while True:
            key_pressed = self.read_key()

            if key_pressed:

                self.last_button_time = time.monotonic()

                # Shane's keypad layout:
                #
                # * = channel up
                # # = channel down

                if key_pressed == "*":
                    print("Channel Up")
                    self.send_command("up")
                    self.tm.show("----")

                    in_selection = False
                    selection_digits = ""

                elif key_pressed == "#":
                    print("Channel Down")
                    self.send_command("down")
                    self.tm.show("----")

                    in_selection = False
                    selection_digits = ""

                elif key_pressed.isdigit():

                    # Start a new direct-channel selection if necessary.
                    if not in_selection:
                        selection_digits = ""

                    selection_digits += key_pressed

                    # CHxx only has room for two digits.
                    # If a third digit is entered, begin again with it.
                    if len(selection_digits) > 2:
                        selection_digits = key_pressed

                    as_num = int(selection_digits)

                    print(f"Channel selection: {as_num}")

                    self.tm.show(f"  {as_num:02d}")

                    in_selection = True
                    last_selection_tick = time.monotonic()

            # Apply direct channel number after 1.5 seconds
            # without another number key.
            if in_selection:
                tick_diff = time.monotonic() - last_selection_tick

                if tick_diff > 1.5:
                    as_num = int(selection_digits)

                    print(f"Applying selection CH{as_num:02d}")

                    self.tm.show(f"CH{as_num:02d}")

                    channel_num = as_num
                    self.send_command("direct", channel_num)

                    in_selection = False
                    selection_digits = ""
                    last_selection_tick = -1

            # Existing IR remote direct-number input.
            if not in_selection:
                remote_digits = self.check_press()

                if remote_digits:
                    self.last_button_time = time.monotonic()
                    self.tm.show(f"  {int(remote_digits):02d}")

            new_stat = self.check_status()

            if new_stat:
                self.temp_mode = False

                try:
                    new_channel_num = int(new_stat["channel_number"])

                    if new_channel_num != channel_num:
                        self.last_button_time = time.monotonic()
                        channel_num = new_channel_num

                    if channel_num >= 0:
                        self.tm.show(f"CH{channel_num:02d}")
                        print("Set channel:", channel_num)
                    else:
                        self.tm.show("FS42")

                except Exception:
                    self.tm.show("FS42")

            elapsed_since_press = (
                time.monotonic() - self.last_button_time
            )

            if (
                self.show_time
                and elapsed_since_press > 15
                and not in_selection
                and (tick_count % 10) == 0
            ):
                formatted = time.strftime(
                    self.time_format,
                    time.localtime()
                )

                if ":" in formatted:
                    h, m = formatted.split(":", 1)
                    self.tm.numbers(int(h), int(m))
                else:
                    self.tm.show(formatted)

            tick_count += 1
            time.sleep(0.05)


if __name__ == "__main__":
    cable_box = CableBox()
    cable_box.event_loop()
