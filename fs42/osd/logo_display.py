import json
import sys
from pathlib import Path
import glfw
from pydantic import BaseModel
from enum import Enum
import random
import glob

from render import load_texture
from OpenGL.GL import *

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fs42.station_manager import StationManager
from fs42.osd.content_classifier import ContentClassifier, ContentType, classify_current_content # ContentClassifier unused

SOCKET_FILE = "runtime/play_status.socket"

class HAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"

class VAlignment(Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER = "CENTER"

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
    display_time: float = 5.0
    default_show_logo: bool = True 
    default_logo_permanent: bool = False

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
        self.current_content_type = ContentType.UNKNOWN
        self.available_logos = [] 
        self.current_logo_path = None
        self.is_displaying_osd_default_logo = False 
        self.check_status()

    def get_available_logos(self, logo_dir_path):
        """Get list of all logo files in the logo directory"""
        logo_extensions = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp']
        available_logos = []
        
        for ext in logo_extensions:
            available_logos.extend(glob.glob(str(logo_dir_path / ext)))
            available_logos.extend(glob.glob(str(logo_dir_path / ext.upper())))
        
        return [Path(logo) for logo in available_logos]

    def select_logo_for_channel(self, station_data):
        """Select which logo to use based on multi_logo setting"""
        multi_logo_setting = station_data.get("multi_logo", "single").lower()

        if multi_logo_setting == "off":
            multi_logo_setting = "single"
        elif multi_logo_setting == "random":
            multi_logo_setting = "multi"

        if multi_logo_setting not in ["single", "multi"]:
            multi_logo_setting = "single"  # Default fallback
        
        content_dir = station_data.get("content_dir")
        logo_dir = station_data.get("logo_dir")
        default_logo_name = station_data.get("default_logo")

        if content_dir and logo_dir:
            logo_dir_path = Path(content_dir) / logo_dir
        elif logo_dir: 
            logo_dir_path = project_root / logo_dir
        else:
            return None
        
        if multi_logo_setting == "single":
            if default_logo_name:
                return logo_dir_path / default_logo_name
        else: 
            if not hasattr(self, 'available_logos') or not self.available_logos:
                self.available_logos = self.get_available_logos(logo_dir_path)
            
            if self.available_logos:
                selected_logo = random.choice(self.available_logos)
                return selected_logo
        
        return None

    def check_status(self, socket_file=SOCKET_FILE):
        try:
            with open(socket_file, "r") as f:
                status = f.read()
                status = json.loads(status)

                current_network = self.current_channel_info.get("network_name")
                current_title = self.current_channel_info.get("title")
                new_network = status.get("network_name")
                new_title = status.get("title")
                
                if new_network != current_network:
                    self.current_channel_info = status
                    self.time_since_change = 0
                    self.load_logo_for_channel(status)
                    # Update content type when title changes
                    self.current_content_type = classify_current_content()
                elif new_title != current_title:
                    # Update content type when title changes
                    old_content_type = self.current_content_type
                    self.current_content_type = classify_current_content()
                    # Reset timer when returning to FEATURE content
                    if old_content_type != ContentType.FEATURE and self.current_content_type == ContentType.FEATURE:
                        self.time_since_change = 0
                        if self.channel_config.get("multi_logo", "single").lower() in ["multi", "random"]:
                            self.load_logo_for_channel(status)
                    self.current_channel_info = status
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
                width, height = img.size
                for frame_num in range(img.n_frames):
                    img.seek(frame_num)
                    frame = img.convert('RGBA')
                    duration = img.info.get('duration', 100) / 1000.0
                    durations.append(duration)
                    frame_data = frame.tobytes()
                    frame_width, frame_height = frame.size
                    texture_id = glGenTextures(1)
                    glBindTexture(GL_TEXTURE_2D, texture_id)
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, frame_width, frame_height, 0, 
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
            self.clear_logo_textures()
            return False
    
    def clear_logo_textures(self):
        """Clear all current logo textures"""
        if self.current_logo_textures:
            glDeleteTextures(self.current_logo_textures)
        self.current_logo_textures = []
        self.current_logo_path = None
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
        self.is_displaying_osd_default_logo = False 

        network_name = channel_info.get("network_name")
        station_wants_to_show_logo = True

        if network_name:
            try:
                station_data = self.station_manager.station_by_name(network_name)
                if station_data and isinstance(station_data, dict):
                    self.channel_config = station_data
                    
                    if station_data.get("show_logo", True) is False:
                        station_wants_to_show_logo = False
                        self.clear_logo_textures()
                        return

                    logo_path = self.select_logo_for_channel(station_data)
                    
                else:
                    print(f"[WARNING] StationManager returned no data for {network_name}")
            except Exception as e:
                print(f"[ERROR] Failed to get station data for {network_name}: {e}")

        if not logo_path and station_wants_to_show_logo:
            if self.config.default_show_logo and self.config.default_logo:
                default_logo_candidate = Path(self.config.default_logo)
                if default_logo_candidate.exists():
                    logo_path = default_logo_candidate
                    self.is_displaying_osd_default_logo = True # Mark that OSD default is being used
                else:
                     print(f"[WARNING] OSD Default logo file not found: {self.config.default_logo}")


        if logo_path and Path(logo_path).exists():
            try:
                if self.current_logo_path == str(logo_path) and not (
                    self.channel_config.get("multi_logo", "single").lower() in ["multi", "random"] and \
                    not self.is_displaying_osd_default_logo):
                    return 

                self.current_logo_path = str(logo_path)
                if str(logo_path).lower().endswith('.gif'):
                    success = self.load_animated_gif(str(logo_path))
                    if not success:
                        self.load_static_logo(str(logo_path)) 
                else:
                    self.load_static_logo(str(logo_path))
            except Exception as e:
                print(f"[ERROR] Error loading logo {logo_path}: {e}")
                self.clear_logo_textures()
                self.is_displaying_osd_default_logo = False
        else:
            if logo_path:
                print(f"[WARNING] Logo file not found: {logo_path}")
            self.clear_logo_textures()
            self.is_displaying_osd_default_logo = False


    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

        if self.is_animated and self.current_logo_textures:
            self.frame_timer += dt
            if self.current_frame_index < len(self.current_frame_durations):
                current_frame_duration = self.current_frame_durations[self.current_frame_index]
                if current_frame_duration <= 0: 
                    current_frame_duration = 0.1 
                if self.frame_timer >= current_frame_duration:
                    self.frame_timer -= current_frame_duration 
                    self.current_frame_index = (self.current_frame_index + 1) % len(self.current_logo_textures)
            elif self.current_logo_textures:
                 self.current_frame_index = 0


    def draw(self):
        if not self.current_logo_textures or self.current_frame_index >= len(self.current_logo_textures):
            return

        # Only show logos during FEATURE content
        if self.current_content_type != ContentType.FEATURE:
            return

        effective_is_permanent = False
        if self.is_displaying_osd_default_logo:
            effective_is_permanent = self.config.default_logo_permanent
        elif self.channel_config: 
            effective_is_permanent = self.channel_config.get("logo_permanent", False)

        effective_display_time = self.config.display_time 
        if not self.is_displaying_osd_default_logo and self.channel_config.get("logo_display_time") is not None:
            effective_display_time = float(self.channel_config["logo_display_time"])

        if not effective_is_permanent and not self.config.always_show and self.time_since_change >= effective_display_time:
            return

        current_config_width = self.config.width
        current_config_height = self.config.height
        current_config_x_margin = self.config.x_margin
        current_config_y_margin = self.config.y_margin
        current_config_halign = self.config.halign
        current_config_valign = self.config.valign

        if not self.is_displaying_osd_default_logo and self.channel_config:
            current_config_width = float(self.channel_config.get("logo_width", self.config.width))
            current_config_height = float(self.channel_config.get("logo_height", self.config.height))
            current_config_x_margin = float(self.channel_config.get("logo_x_margin", self.config.x_margin))
            current_config_y_margin = float(self.channel_config.get("logo_y_margin", self.config.y_margin))
            
            halign_str_override = self.channel_config.get("logo_halign")
            if halign_str_override:
                try:
                    current_config_halign = HAlignment[halign_str_override.upper()]
                except KeyError:
                    pass # Invalid override, use OSD config halign

            valign_str_override = self.channel_config.get("logo_valign")
            if valign_str_override:
                try:
                    current_config_valign = VAlignment[valign_str_override.upper()]
                except KeyError:
                    pass # Invalid override, use OSD config valign

        logo_width_ndc = current_config_width * 2
        logo_height_ndc = current_config_height * 2

        if current_config_halign == HAlignment.LEFT:
            x = -1 + current_config_x_margin
        elif current_config_halign == HAlignment.RIGHT:
            x = 1 - logo_width_ndc - current_config_x_margin
        else: # CENTER
            x = -logo_width_ndc / 2

        if current_config_valign == VAlignment.BOTTOM:
            y = -1 + current_config_y_margin
        elif current_config_valign == VAlignment.TOP:
            y = 1 - logo_height_ndc - current_config_y_margin
        else: # CENTER
            y = -logo_height_ndc / 2
        
        # Bind the current frame's texture
        current_texture = self.current_logo_textures[self.current_frame_index]
        glBindTexture(GL_TEXTURE_2D, current_texture)
        self.draw_logo_quad(x, y, logo_width_ndc, logo_height_ndc)

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
