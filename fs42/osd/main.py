import json
import glfw
from pydantic import BaseModel
from enum import Enum

from render import Text, create_window, clear_screen

SOCKET_FILE = "runtime/play_status.socket"

class HAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"

class VAlignment(Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER = "CENTER"

class OSDConfig(BaseModel):
    display_time: float = 2.0
    halign: HAlignment = HAlignment.LEFT
    valign: VAlignment = VAlignment.TOP
    format_text: str = "{channel_number} - {network_name}"
    text_color: tuple[int, int, int, int] = (0, 255, 0, 200)
    font_size: int = 40
    font: str | None = None 
    x_margin: float = 0.1
    y_margin: float = 0.1

class ChannelDisplay(object):
    def __init__(self, window, config: OSDConfig):
        self.config = config

        self._text = Text(window, "", font_size=self.config.font_size,
                          color=self.config.text_color,
                          font=self.config.font)

        self.cur_status = {"channel_number": -1, "network_name": "Offline"}
        self.time_since_change = 0

        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        with open(socket_file, "r") as f:
            status = f.read()
            try:
                status = json.loads(status)
                # only care about channel number and network, timestamp
                # changes shouldn't cause a render
                status = {"channel_number": status["channel_number"],
                          "network_name": status["network_name"]}
            except:
                print(f"Unable to parse player status, {status}")

            else:
                if status != self.cur_status:
                    self.cur_status = status
                    self.time_since_change = 0
                    if status:
                        self._text.string = self.config.format_text.format(**status)

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self):
        if self.time_since_change < self.config.display_time:
            # Screen coords are -1 to 1 with 0 in the center, -1,-1 is bottom left.
            # text draw origin is at bottom left
            if self.config.halign == HAlignment.LEFT:
                x = -1 + self.config.x_margin
            elif self.config.halign == HAlignment.RIGHT:
                x = 1 - self._text.width - self.config.x_margin
            else: # CENTER
                x = -self._text.width / 2

            if self.config.valign == VAlignment.BOTTOM:
                y = -1 + self.config.y_margin
            elif self.config.valign == VAlignment.TOP:
                y = 1 - self._text.height - self.config.y_margin
            else: # CENTER
                y = -self._text.height / 2

            self._text.draw(x, y)

with open("osd/channel_display.json", "r") as f:
    config = OSDConfig.model_validate_json(f.read())

window = create_window()

osd = ChannelDisplay(window, config)

# --------------------------
# Main loop

now = glfw.get_time()
while not glfw.window_should_close(window):
    now, last = glfw.get_time(), now
    delta_time = now - last
    glfw.poll_events()

    clear_screen()

    osd.update(delta_time)
    osd.draw()

    glfw.swap_buffers(window)

# Cleanup
glDeleteTextures([texture])
glfw.terminate()

