import json
import time
import os
import sys
import subprocess

# Orange Pi gpiod (v2.x API)
import gpiod
from gpiod.line import Edge
from datetime import timedelta

# TM1637
import tm1637

# Adjust chip and line offset based on your configuration
# (e.g., /dev/gpiochip0 and line offset for your specific pin)
# PH2 - restart button, in case FS42 freezes
# PC11 - channel up
# PC15 - channel down
CHIP_PATH = "/dev/gpiochip0"
RESET_LINE_OFFSET = 226  # Pin 8, labeled PH2
CHANNEL_UP_LINE_OFFSET = 75  # Pin 12, labeled PC11
CHANNEL_DOWN_LINE_OFFSET = 79  # Pin 16, labeled PC15


class CableBox:
    def __init__(self, channel_socket="runtime/channel.socket", status_socket="runtime/play_status.socket", press_socket="runtime/press.socket"):
        self.channel_socket = channel_socket
        self.status_socket = status_socket
        self.press_socket = press_socket
        
        self.tm = tm1637.TM1637(CHIP_PATH, clk=230, dio=74)
        self.tm.brightness(0)
        self.tm.show("FS42")
        
        self.last_stat = ""

        # In 2.x, a single LineSettings object can be reused across offsets
        line_settings = gpiod.LineSettings(edge_detection=Edge.BOTH)

        # In 2.x, all lines are requested together in one call, keyed by offset
        self.request = gpiod.request_lines(
            CHIP_PATH,
            consumer="fieldstation42",
            config={
                RESET_LINE_OFFSET: line_settings,
                CHANNEL_UP_LINE_OFFSET: line_settings,
                CHANNEL_DOWN_LINE_OFFSET: line_settings,
            },
        )

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
                except:
                    # assume that it was a partial read and try again next time
                    print(f"Error decoding status: {as_str}")
        return new_stat

    def send_command(self, command, channel=-1):
        as_obj = {"command": command, "channel": channel}
        as_str = json.dumps(as_obj)
        print(f"Sending command: {as_str}")
        with open(self.channel_socket, "w") as fp:
            fp.write(as_str)

    # This is where the GPIO buttons are pressed
    def read_keys(self):
        # wait_edge_events/read_edge_events replace the old per-line event_wait/event_read
        if self.request.wait_edge_events(timedelta(milliseconds=50)):
            for event in self.request.read_edge_events():
                # Note: EdgeEvent.Type is a different enum from line.Edge used above
                if event.event_type != gpiod.EdgeEvent.Type.FALLING_EDGE:
                    continue

                if event.line_offset == RESET_LINE_OFFSET:
                    print("Reset button pressed!")
                    return "RESET_BUTTON"
                elif event.line_offset == CHANNEL_UP_LINE_OFFSET:
                    print("Channel Up Button pressed!")
                    return "CHANNEL_UP_BUTTON"
                elif event.line_offset == CHANNEL_DOWN_LINE_OFFSET:
                    print("Channel Down Button pressed!")
                    return "CHANNEL_DOWN_BUTTON"

        return None

    def event_loop(self):
        last_pressed = ""
        in_selection = False
        last_selection_tick = -1
        channel_num = 0
        tick_count = 0
        while True:
            key_pressed = self.read_keys()
            # Print something here for now
            if key_pressed:
                print("Key pressed:", key_pressed)

                if key_pressed == "RESET_BUTTON":  # Restarts FS42
                    print("Button pressed from service!", flush=True)
                    os.system("systemctl --user restart fs42")
                    time.sleep(0.3)
                elif key_pressed == "CHANNEL_UP_BUTTON":  # Moves channel UP
                    self.send_command("up")
                    channel_num += 1
                    self.tm.show("----")
                    in_selection = False
                elif key_pressed == "CHANNEL_DOWN_BUTTON":  # Moves channel DOWN
                    if channel_num > 0:
                        self.send_command("down")
                        channel_num -= 1
                        self.tm.show("----")
                    in_selection = False
                    
            if in_selection:
                tick_diff = time.monotonic() - last_selection_tick
                if tick_diff > 1.5:
                    print(f"Applying selection CH{as_num:02d}")
                    self.tm.show(f"CH{as_num:02d}")
                    last_selection_tick = -1
                    in_selection = False
                    last_pressed = ""
                    channel_num = as_num
                    self.send_command("direct", channel_num)
                    
            time.sleep(0.1)
            
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
                        print("Set channel: ", channel_num)
                    else:
                        self.tm.show("FS42")
                except:
                    self.tm.show("FS42")

            elapsed_since_press = time.monotonic() - self.last_button_time
            if self.show_time and elapsed_since_press > 15 and not in_selection and (tick_count % 10) == 0:
                formatted = time.strftime(self.time_format, time.localtime())
                if ":" in formatted:
                    h, m = formatted.split(":", 1)
                    self.tm.numbers(int(h), int(m))
                else:
                    self.tm.show(formatted)
            
            tick_count += 1


if __name__ == "__main__":
    cable_box = CableBox()
    cable_box.event_loop()
