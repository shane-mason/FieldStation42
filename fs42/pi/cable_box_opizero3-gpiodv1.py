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
LINE_OFFSET = 226  # Example offset for PH2 or calculate via pin formula

class CableBox:
    def __init__(self, channel_socket="runtime/channel.socket", status_socket="runtime/play_status.socket", press_socket="runtime/press.socket"):
        self.channel_socket = channel_socket
        self.status_socket = status_socket
        self.press_socket = press_socket
        
        self.chip = gpiod.chip(CHIP_PATH)
        self.line = self.chip.get_line(LINE_OFFSET)

        config = gpiod.line_request()
        config.consumer = "fieldstation42"
        config.request_type = gpiod.line_request.EVENT_BOTH_EDGES

        self.line.request(config)
        
    # This is where the GPIO buttons are pressed
    def read_keys(self):
        if self.line.event_wait(timedelta(milliseconds=50)):
            event = self.line.event_read()
            
            if event.event_type == gpiod.line_event.FALLING_EDGE:
                print("Button pressed!")
                return "BUTTON"
            
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
                print("Button pressed from service!", flush=True)
                os.system("systemctl --user restart fs42")
                time.sleep(0.3)
            

if __name__ == "__main__":
    cable_box = CableBox()
    cable_box.event_loop()
