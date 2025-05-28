import json
from pathlib import Path
import glfw
from pydantic import BaseModel
from enum import Enum

from render import Text, create_window, clear_screen, load_texture
from OpenGL.GL import *

SOCKET_FILE = "runtime/play_status.socket"
CONFIG_FILE_PATH = Path("osd/osd.json")

class HAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"

class VAlignment(Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER = "CENTER"

class StatusDisplayConfig(BaseModel):
    display_time: float = 2.0
    halign: HAlignment = HAlignment.LEFT
    valign: VAlignment = VAlignment.TOP
    format_text: str = "{channel_number} - {network_name}"
    text_color: tuple[int, int, int, int] = (0, 255, 0, 200)
    font_size: int = 40
    expansion_factor: float = 1.0
    font: str | None = None 
    x_margin: float = 0.1
    y_margin: float = 0.1
    delay: float = 0.0

class LogoDisplayConfig(BaseModel):
    halign: HAlignment = HAlignment.RIGHT
    valign: VAlignment = VAlignment.TOP
    width: float = 0.112  
    height: float = 0.15  
    x_margin: float = 0.05
    y_margin: float = 0.05
    logo_mapping: dict[str, str] = {}
    default_logo: str | None = None
    always_show: bool = False

class StatusDisplay(object):
    def __init__(self, window, config: StatusDisplayConfig):
        self.config = config
        self.window = window

        self._text = Text(window, "", font_size=self.config.font_size,
                          color=self.config.text_color,
                          expansion_factor=self.config.expansion_factor,
                          font=self.config.font)

        self.time_since_change = 0

        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        with open(socket_file, "r") as f:
            status = f.read()
            try:
                status = json.loads(status)
            except:
                print(f"Unable to parse player status, {status}")

            else:
                new_string = self.config.format_text.format(**status)
                if new_string != self._text.string:
                    self.time_since_change = -self.config.delay
                    if new_string:
                        self._text.string = new_string

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

class LogoDisplay(object):
    def __init__(self, window, config: LogoDisplayConfig):
        self.config = config
        self.window = window
        self.window_width, self.window_height = glfw.get_framebuffer_size(window)
        
        self.current_logo_texture = None
        self.current_logo_size = (0, 0)
        self.current_channel_info = {}
        self.channel_config = {}  # <--- stores per-channel config like show_logo, logo_permanent
        self.time_since_change = float('inf')
        
        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        try:
            with open(socket_file, "r") as f:
                status = f.read()
                status = json.loads(status)

                if status != self.current_channel_info:
                    self.current_channel_info = status
                    self.time_since_change = 0
                    self.load_logo_for_channel(status)
        except Exception as e:
            print(f"Unable to parse player status for logo: {e}")

    def load_logo_for_channel(self, channel_info):
        logo_path = None
        self.channel_config = {}

        network_name = channel_info.get("network_name")
        if network_name:
            config_path = Path("confs") / f"{network_name}.json"

            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        channel_file = json.load(f)
                        
                    self.channel_config = channel_file.get("station_conf", channel_file)
                    logo_path = self.channel_config.get("logo_path")

                    if self.channel_config.get("show_logo", True) is False:
                        if self.current_logo_texture:
                            glDeleteTextures([self.current_logo_texture])
                        self.current_logo_texture = None
                        return

                except Exception as e:
                    print(f"[ERROR] Failed to read config for {network_name}: {e}")
            else:
                print(f"[WARNING] No config file for {network_name}")

        if not logo_path:
            logo_path = self.config.default_logo

        if logo_path and Path(logo_path).exists():
            try:
                if self.current_logo_texture:
                    glDeleteTextures([self.current_logo_texture])
                self.current_logo_texture, width, height = load_texture(logo_path)
                self.current_logo_size = (width, height)
            except Exception as e:
                print(f"Error loading logo {logo_path}: {e}")
                self.current_logo_texture = None
        else:
            if self.current_logo_texture:
                glDeleteTextures([self.current_logo_texture])
            self.current_logo_texture = None

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self):
        if not self.current_logo_texture:
            return

        is_permanent = self.channel_config.get("logo_permanent", False)

        if not is_permanent and not self.config.always_show and self.time_since_change >= 5.0:
            return

        logo_width = self.config.width * 2
        logo_height = self.config.height * 2

        if self.config.halign == HAlignment.LEFT:
            x = -1 + self.config.x_margin
        elif self.config.halign == HAlignment.RIGHT:
            x = 1 - logo_width - self.config.x_margin
        else:
            x = -logo_width / 2

        if self.config.valign == VAlignment.BOTTOM:
            y = -1 + self.config.y_margin
        elif self.config.valign == VAlignment.TOP:
            y = 1 - logo_height - self.config.y_margin
        else:
            y = -logo_height / 2

        glBindTexture(GL_TEXTURE_2D, self.current_logo_texture)
        self.draw_logo_quad(x, y, logo_width, logo_height)

    def draw_logo_quad(self, x, y, w, h):
        glBegin(GL_QUADS)
        glColor4f(1, 1, 1, 1)
        glTexCoord2f(0, 1); glVertex2f(x, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 0); glVertex2f(x, y + h)
        glEnd()

    def __del__(self):
        if self.current_logo_texture:
            glDeleteTextures([self.current_logo_texture])

objects = []

window = create_window()

if CONFIG_FILE_PATH.exists():
    with open(CONFIG_FILE_PATH, "r") as f:
        config_dict = json.load(f)
        for obj in config_dict:
            if 'type' not in obj:
                obj['type'] = "StatusDisplay"
            if obj['type'] == "StatusDisplay":
                del obj['type']
                config = StatusDisplayConfig.model_validate(obj)
                osd = StatusDisplay(window, config)
                objects.append(osd)
            elif obj['type'] == "LogoDisplay":
                del obj['type']
                config = LogoDisplayConfig.model_validate(obj)
                logo = LogoDisplay(window, config)
                objects.append(logo)
            else:
                print(f"Unrecognized osd object type: {obj['type']}")
else:
    config = StatusDisplayConfig()
    objects.append(StatusDisplay(window, config))


# --------------------------
# Main loop

now = glfw.get_time()
while not glfw.window_should_close(window):
    glfw.wait_events_timeout(1.0 / 30.0)  # ~30 FPS, low CPU
    now, last = glfw.get_time(), now
    delta_time = now - last

    clear_screen()

    for obj in objects:
        obj.update(delta_time)

    for obj in objects:
        obj.draw()

    glfw.swap_buffers(window)

# Cleanup
glfw.terminate()
