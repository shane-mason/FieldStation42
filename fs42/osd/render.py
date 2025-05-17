import glfw
from OpenGL.GL import *
from PIL import Image, ImageDraw, ImageFont
import json

DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

__font_objects = {}

class Text(object):
    def __init__(self, window, string="",expansion_factor=1, font_size=32, color=(255,255,255,255), font=None):
        self._string = string
        self._font_size = font_size
        self._color = color
        self._font = font
        self.expansion_factor = expansion_factor 
        self.window = window
        self.window_width, self.window_height = glfw.get_framebuffer_size(window)
        self.text_texture = None
        self.render_text_texture()

    @property
    def string(self):
        return self._string

    @string.setter
    def string(self, value):
        self._string = value
        self.render_text_texture()

    @property
    def font_size(self):
        return self._font_size

    @font_size.setter
    def font_size(self, value):
        self._font_size = value
        self.render_text_texture()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value
        self.render_text_texture()

    @property
    def font(self):
        return self._font

    @font.setter
    def font(self, value):
        self._font = value
        self.render_text_texture()

    @property
    def width(self):
        return self.tex_size[0] * 2 / self.window_width * self.expansion_factor

    @property
    def height(self):
        return self.tex_size[1] * 2 / self.window_height * self.expansion_factor

    def render_text_texture(self):
        if self.text_texture is not None:
            glDeleteTextures(self.text_texture)

        self.text_texture, self.tex_size = create_text_texture(self.string, 
                                                               self.font_size, 
                                                               self.font, 
                                                               self.color)

    def draw(self, x, y):
        glBindTexture(GL_TEXTURE_2D, self.text_texture)

        # Set desired position (in NDC: -1 to 1)
        h = self.height
        w = self.width

        # Render textured quad with text on it
        draw_gl_quad_textured(x, y, w, h)

    def __del__(self):
        glDeleteTextures(self.text_texture)

def draw_gl_quad_textured(x, y, w, h):
    glBegin(GL_QUADS)
    glColor4f(1, 1, 1, 1)
    glTexCoord2f(0, 1); glVertex2f(x, y)
    glTexCoord2f(1, 1); glVertex2f(x + w, y)
    glTexCoord2f(1, 0); glVertex2f(x + w, y + h)
    glTexCoord2f(0, 0); glVertex2f(x, y + h)
    glEnd()

def create_text_texture(text, font_size=32, font=None, color = (255, 255, 255, 255)):
    if font is None:
        font = DEFAULT_FONT


    if (font, font_size) not in __font_objects:
        font = ImageFont.truetype(font, font_size)
        __font_objects[(font, font_size)] = font
    font = __font_objects[(font, font_size)]

    # Create a dummy image to calculate text size
    dummy_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy_image)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Now create the actual image
    image = Image.new("RGBA", (text_width, text_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text((-bbox[0], -bbox[1]), text, font=font, fill=color)  

    tex_data = image.tobytes("raw", "RGBA", 0, 1)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex_data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    return tex, (image.width, image.height)


# --------------------------
# Load PNG with alpha channel
def load_texture(path):
    image = Image.open(path).convert("RGBA")
    image_data = image.tobytes()
    width, height = image.size

    texture = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    return texture, width, height

def create_window():
    # --------------------------
    # Init GLFW and OpenGL
    if not glfw.init():
        raise Exception("GLFW failed to init")

    # TODO: figure out which monitor to use
    # should be the one that mpv is currently on....

    monitor = glfw.get_primary_monitor()
    mode = glfw.get_video_mode(monitor)

    glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, glfw.TRUE)
    glfw.window_hint(glfw.DECORATED, glfw.FALSE)
    glfw.window_hint(glfw.FLOATING, glfw.TRUE)
    glfw.window_hint(glfw.FOCUSED, glfw.TRUE)
    window = glfw.create_window(mode.size.width, mode.size.height, "FieldStation42 OSD", monitor, None)
    glfw.make_context_current(window)
    glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)

    # Enable blending for alpha
    glEnable(GL_BLEND)
    glEnable(GL_TEXTURE_2D)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    return window

def clear_screen(color = (0, 0, 0, 0)):
    glClearColor(0, 0, 0, 0)  # Transparent clear
    glClear(GL_COLOR_BUFFER_BIT)
