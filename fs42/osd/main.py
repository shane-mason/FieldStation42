import json
import re
import sys
from collections import defaultdict
from pathlib import Path
import glfw
from pydantic import BaseModel
from enum import Enum

from render import Text, create_window, clear_screen
from logo_display import LogoDisplay, LogoDisplayConfig
from OpenGL.GL import *

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fs42.station_manager import StationManager
from fs42.osd.content_classifier import (
    ContentClassifier,
    ContentType,
    classify_current_content,
)

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


class StatusDisplay(object):
    def __init__(self, window, config: StatusDisplayConfig):
        self.config = config
        self.window = window

        self._text = Text(
            window,
            "",
            font_size=self.config.font_size,
            color=self.config.text_color,
            expansion_factor=self.config.expansion_factor,
            font=self.config.font,
        )

        self.time_since_change = 0
        self.last_status = None  # Track the last status to detect changes

        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        with open(socket_file, "r") as f:
            status = f.read()
            try:
                status = json.loads(status)
            except:
                print(f"Unable to parse player status, {status}")

            else:
                # Check if status field changed (e.g., from "stopped" to "playing")
                status_changed = self.last_status is None or status.get("status") != self.last_status.get("status")
                self.last_status = status

                new_string = self.config.format_text.format_map(defaultdict(str, status))
                # Reset timer if text changed OR if status changed (like stopped->playing)
                if new_string != self._text.string or status_changed:
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
            else:  # CENTER
                x = -self._text.width / 2

            if self.config.valign == VAlignment.BOTTOM:
                y = -1 + self.config.y_margin
            elif self.config.valign == VAlignment.TOP:
                y = 1 - self._text.height - self.config.y_margin
            else:  # CENTER
                y = -self._text.height / 2

            self._text.draw(x, y)


VOLUME_SOCKET_FILE = "runtime/volume.socket"


class VolumeDisplayConfig(BaseModel):
    display_time: float = 5.0
    halign: HAlignment = HAlignment.CENTER
    valign: VAlignment = VAlignment.BOTTOM
    color: tuple[int, int, int, int] = (0, 255, 0, 200)
    width: float = 0.4
    height: float = 0.04
    x_margin: float = 0.1
    y_margin: float = 0.375
    border_thickness: float = 2.0
    padding: float = 0.008


class VolumeDisplay(object):


    def __init__(self, window, config: VolumeDisplayConfig):
        self.config = config
        self.window = window
        self.volume = 0.0
        # Start hidden until we actually see a volume message.
        self.time_since_change = float("inf")

    def check_volume(self, socket_file=VOLUME_SOCKET_FILE):
        try:
            with open(socket_file, "r") as f:
                content = f.read()
        except OSError:
            return

        if not content.strip():
            return

        try:
            status = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            print(f"Unable to parse volume status, {content}")
            return

        raw_volume = status.get("volume")
        if raw_volume is None:
            return

        # The volume field can arrive in several shapes depending on the mixer:
        # "75%", "MUTED (75%)", "unknown", "MUTE", etc. Pull the first number out
        # of whatever we get so a decorated string still drives the meter. If
        # there's no number at all (e.g. "unknown"), there's nothing to show.
        match = re.search(r"\d+(?:\.\d+)?", str(raw_volume))
        if not match:
            print(f"No volume level in volume status, {raw_volume}")
            return
        pct = float(match.group())

        self.volume = max(0.0, min(1.0, pct / 100.0))
        self.time_since_change = 0.0

        # Truncate the socket so we only display each change once.
        try:
            with open(socket_file, "w"):
                pass
        except OSError:
            pass

    def update(self, dt):
        self.time_since_change += dt
        self.check_volume()

    def draw(self):
        if self.time_since_change >= self.config.display_time:
            return

        # Screen coords are -1 to 1 with 0 in the center; -1,-1 is bottom left.
        w = self.config.width * 2.0
        h = self.config.height * 2.0

        if self.config.halign == HAlignment.LEFT:
            x = -1.0 + self.config.x_margin
        elif self.config.halign == HAlignment.RIGHT:
            x = 1.0 - w - self.config.x_margin
        else:  # CENTER
            x = -w / 2.0

        if self.config.valign == VAlignment.BOTTOM:
            y = -1.0 + self.config.y_margin
        elif self.config.valign == VAlignment.TOP:
            y = 1.0 - h - self.config.y_margin
        else:  # CENTER
            y = -h / 2.0

        r, g, b, a = (c / 255.0 for c in self.config.color)

        # These are solid-color primitives, not textured quads, so turn off
        # texturing while we draw and restore it afterwards.
        glDisable(GL_TEXTURE_2D)
        glColor4f(r, g, b, a)

        # Outline
        glLineWidth(self.config.border_thickness)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

        # Filled center, proportional to the current volume.
        pad = self.config.padding
        inner_h = h - 2.0 * pad
        inner_w = (w - 2.0 * pad) * self.volume
        if inner_w > 0.0 and inner_h > 0.0:
            glBegin(GL_QUADS)
            glVertex2f(x + pad, y + pad)
            glVertex2f(x + pad + inner_w, y + pad)
            glVertex2f(x + pad + inner_w, y + pad + inner_h)
            glVertex2f(x + pad, y + pad + inner_h)
            glEnd()

        glEnable(GL_TEXTURE_2D)


objects = []

window = create_window()

if CONFIG_FILE_PATH.exists():
    with open(CONFIG_FILE_PATH, "r") as f:
        config_dict = json.load(f)
        for obj in config_dict:
            if "type" not in obj:
                obj["type"] = "StatusDisplay"
            if obj["type"] == "StatusDisplay":
                del obj["type"]
                config = StatusDisplayConfig.model_validate(obj)
                osd = StatusDisplay(window, config)
                objects.append(osd)
            elif obj["type"] == "LogoDisplay":
                del obj["type"]
                config = LogoDisplayConfig.model_validate(obj)
                logo = LogoDisplay(window, config)
                objects.append(logo)
            elif obj["type"] == "HybridDisplay":
                del obj["type"]
                config_status = StatusDisplayConfig.model_validate(obj)
                config_logo = LogoDisplayConfig.model_validate(obj)
                status_osd = StatusDisplay(window, config_status)
                status_logo = LogoDisplay(window, config_logo)
                objects.append(logo)
                objects.append(osd)
            elif obj["type"] == "VolumeDisplay":
                del obj["type"]
                config = VolumeDisplayConfig.model_validate(obj)
                objects.append(VolumeDisplay(window, config))
            else:
                print(f"Unrecognized osd object type: {obj['type']}")

else:
    config = StatusDisplayConfig()
    objects.append(StatusDisplay(window, config))

# Always show a volume meter unless one was explicitly configured. Match its
# color to the first StatusDisplay so it blends with the rest of the OSD.
if not any(isinstance(obj, VolumeDisplay) for obj in objects):
    volume_config = VolumeDisplayConfig()
    for obj in objects:
        if isinstance(obj, StatusDisplay):
            volume_config.color = obj.config.text_color
            break
    objects.append(VolumeDisplay(window, volume_config))


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

    # Draw objects with StatusDisplay on top
    for obj in sorted(objects, key=lambda x: isinstance(x, StatusDisplay)):
        obj.draw()

    glfw.swap_buffers(window)

# Cleanup
glfw.terminate()
