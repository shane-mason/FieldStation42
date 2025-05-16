import json
import glfw

from render import Text, create_window, clear_screen

SCREEN_WIDTH=1024
SCREEN_HEIGHT=768
SCREEN_ASPECT_RATIO=SCREEN_WIDTH/SCREEN_HEIGHT

Y_MARGIN = .1
X_MARGIN = .1

SOCKET_FILE = "runtime/play_status.socket"

class ChannelDisplay(object):
    def __init__(self, window):
        self.cur_status = ""
        self.time_to_display = 2
        self.y_position = "TOP"
        self.x_position = "LEFT"

        self._text = Text(window, "", font_size=40,
                          color=(0, 255, 0, 200))
        self.format_text = "{channel_number} - {network_name}"
        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        with open(socket_file, "r") as f:
            status = f.read()
            if status != self.cur_status:
                self.cur_status = status
                self.time_since_change = 0
                try:
                    status = json.loads(status)
                except:
                    print(f"Unable to parse player status, {status}")
                self._text.string = self.format_text.format(**status)

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self):
        if self.time_since_change < self.time_to_display:
            if self.x_position == "LEFT":
                x = -1 + X_MARGIN
            elif self.x_position == "RIGHT":
                x = 1 - self._text.width - X_MARGIN
            else: # CENTER
                x = -self._text.width / 2

            if self.y_position == "BOTTOM":
                y = -1 + Y_MARGIN
            elif self.y_position == "TOP":
                y = 1 - self._text.height - Y_MARGIN
            else: # CENTER
                y = -self._text.height / 2

            self._text.draw(x, y)


window = create_window()

osd = ChannelDisplay(window)

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

