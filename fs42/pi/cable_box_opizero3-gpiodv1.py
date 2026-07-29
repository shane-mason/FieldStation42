import json
import time
import os
import sys
import subprocess

# Orange Pi gpiod
import gpiod
from datetime import timedelta

# Adjust chip and line offset based on your configuration 
# (e.g., /dev/gpiochip0 and line offset for your specific pin)
# PH2 - restart button, in case FS42 freezes
CHIP_PATH = "/dev/gpiochip0"
RESET_LINE_OFFSET = 226  # Pin 8, labeled PH2
CHANNEL_UP_LINE_OFFSET = 75 # Pin 12, labeled PC11

class CableBox:
    def __init__(self, channel_socket="runtime/channel.socket", status_socket="runtime/play_status.socket", press_socket="runtime/press.socket"):
        self.channel_socket = channel_socket
        self.status_socket = status_socket
        self.press_socket = press_socket
        
        self.chip = gpiod.chip(CHIP_PATH)
        self.reset_line = self.chip.get_line(RESET_LINE_OFFSET)
        self.channel_up_line = self.chip.get_line(CHANNEL_UP_LINE_OFFSET)

        config = gpiod.line_request()
        config.consumer = "fieldstation42"
        config.request_type = gpiod.line_request.EVENT_BOTH_EDGES

        self.reset_line.request(config)
        self.channel_up_line.request(config)
        self.temp_mode = False
        self.last_button_time = time.monotonic()
        self.show_time = True
        self.time_format = "%H:%M"
        
    def send_command(self, command, channel=-1):
        as_obj = {"command": command, "channel": channel}
        as_str = json.dumps(as_obj)
        print(f"Sending command: {as_str}")
        with open(self.channel_socket, "w") as fp:
            fp.write(as_str)
        
    # This is where the GPIO buttons are pressed
    def read_keys(self):
        if self.reset_line.event_wait(timedelta(milliseconds=50)):
            reset_event = self.reset_line.event_read()
            
            if reset_event.event_type == gpiod.line_event.FALLING_EDGE:
                print("Reset button pressed!")
                return "RESET_BUTTON"
        
        if self.channel_up_line.event_wait(timedelta(milliseconds=50)):
            channel_up_event = self.channel_up_line.event_read()
            
            if channel_up_event.event_type == gpiod.line_event.FALLING_EDGE:
                print("Channel Up Button pressed!")
                return "CHANNEL_UP_BUTTON"
        
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
                
                if key_pressed == "RESET_BUTTON":
                    print("Button pressed from service!", flush=True)
                    os.system("systemctl --user restart fs42")
                    time.sleep(0.3)
                elif key_pressed == "CHANNEL_UP_BUTTON":
                    self.send_command("up")
                    channel_num += 1
                    # self.tm.show("----")
                    in_selection = False
            

if __name__ == "__main__":
    cable_box = CableBox()
    cable_box.event_loop()
