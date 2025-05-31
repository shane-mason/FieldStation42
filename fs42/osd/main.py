import json
import sys
from pathlib import Path
import glfw
from pydantic import BaseModel
from enum import Enum

from render import Text, create_window, clear_screen, load_texture
from OpenGL.GL import *

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from fs42.station_manager import StationManager
except ImportError as e:
    print(f"Failed to import StationManager: {e}")
    print(f"Looked in: {project_root}")
    print("Please ensure the fs42 package structure is correct")
    sys.exit(1)

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
        self.station_manager = StationManager()
        self.current_logo_textures = []  # List of textures for animated GIFs
        self.current_logo_size = (0, 0)
        self.current_frame_durations = []  # Duration for each frame in seconds
        self.current_frame_index = 0
        self.frame_timer = 0.0
        self.is_animated = False
        self.current_channel_info = {}
        self.channel_config = {}  # stores per-channel config like show_logo, logo_permanent
        self.time_since_change = float('inf')
        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        try:
            with open(socket_file, "r") as f:
                status = f.read()
                status = json.loads(status)

                current_network = self.current_channel_info.get("network_name")
                new_network = status.get("network_name")
                
                if new_network != current_network:
                    self.current_channel_info = status
                    self.time_since_change = 0
                    self.load_logo_for_channel(status)
                else:
                    self.current_channel_info = status
                    
        except Exception as e:
            print(f"Unable to parse player status for logo: {e}")

    def load_animated_gif(self, gif_path):
        """Load an animated GIF and extract all frames"""
        try:
            from PIL import Image

            self.clear_logo_textures()
            
            with Image.open(gif_path) as img:
                frames = []
                durations = []

                for frame_num in range(img.n_frames):
                    img.seek(frame_num)

                    frame = img.convert('RGBA')
                    
                    duration = img.info.get('duration', 100) / 1000.0
                    durations.append(duration)
                    
                    frame_data = frame.tobytes()
                    width, height = frame.size
                    
                    texture_id = glGenTextures(1)
                    glBindTexture(GL_TEXTURE_2D, texture_id)
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, 
                               GL_RGBA, GL_UNSIGNED_BYTE, frame_data)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    
                    frames.append(texture_id)
                
                self.current_logo_textures = frames
                self.current_frame_durations = durations
                self.current_logo_size = (width, height)
                self.current_frame_index = 0
                self.frame_timer = 0.0
                self.is_animated = len(frames) > 1
                
                print(f"[INFO] Loaded animated GIF: {gif_path} ({len(frames)} frames)")
                return True
                
        except ImportError:
            print("[ERROR] PIL (Pillow) is required for animated GIF support. Install with: pip install Pillow")
            return False
        except Exception as e:
            print(f"[ERROR] Error loading animated GIF {gif_path}: {e}")
            return False
    
    def clear_logo_textures(self):
        """Clear all current logo textures"""
        if self.current_logo_textures:
            glDeleteTextures(self.current_logo_textures)
        self.current_logo_textures = []
        self.current_frame_durations = []
        self.current_frame_index = 0
        self.frame_timer = 0.0
        self.is_animated = False

    def load_static_logo(self, logo_path):
        """Load a static logo (PNG, JPG, etc.)"""
        self.clear_logo_textures()
        
        try:
            texture_id, width, height = load_texture(logo_path)
            self.current_logo_textures = [texture_id]
            self.current_frame_durations = [0]  # Static image has no duration
            self.current_logo_size = (width, height)
            self.current_frame_index = 0
            self.frame_timer = 0.0
            self.is_animated = False
            print(f"[INFO] Loaded static logo: {logo_path}")
            
        except Exception as e:
            print(f"[ERROR] Error loading static logo {logo_path}: {e}")
            self.clear_logo_textures()

    def load_logo_for_channel(self, channel_info):
        logo_path = None
        self.channel_config = {}

        network_name = channel_info.get("network_name")
        if network_name:
            try:
                station_data = self.station_manager.station_by_name(network_name)
                
                if station_data and isinstance(station_data, dict):
                    self.channel_config = station_data
                    logo_path = station_data.get("logo_path")
                    
                    if station_data.get("show_logo", True) is False:
                        self.clear_logo_textures()
                        return
                else:
                    print(f"[WARNING] StationManager returned no data for {network_name}")
                    
            except Exception as e:
                print(f"[ERROR] Failed to get station data for {network_name}: {e}")


        if not logo_path:
            logo_path = self.config.default_logo

        if logo_path and Path(logo_path).exists():
            try:
                if logo_path.lower().endswith('.gif'):
                    success = self.load_animated_gif(logo_path)
                    if not success:
                        self.load_static_logo(logo_path)
                else:
                    self.load_static_logo(logo_path)
                    
            except Exception as e:
                print(f"[ERROR] Error loading logo {logo_path}: {e}")
                self.clear_logo_textures()
        else:
            if logo_path:
                print(f"[WARNING] Logo file not found: {logo_path}")
            self.clear_logo_textures()

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

        if self.is_animated and self.current_logo_textures:
            self.frame_timer += dt

            if self.current_frame_index < len(self.current_frame_durations):
                current_frame_duration = self.current_frame_durations[self.current_frame_index]
                
                if self.frame_timer >= current_frame_duration:
                    self.frame_timer = 0.0
                    self.current_frame_index = (self.current_frame_index + 1) % len(self.current_logo_textures)

    def draw(self):
        if not self.current_logo_textures:
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

        # Bind the current frame's texture
        current_texture = self.current_logo_textures[self.current_frame_index]
        glBindTexture(GL_TEXTURE_2D, current_texture)
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
        if hasattr(self, 'current_logo_textures') and self.current_logo_textures:
            glDeleteTextures(self.current_logo_textures)

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
