import json
import sys
from pathlib import Path
import datetime
import random
import glob

import glfw
from pydantic import BaseModel
from enum import Enum

from render import load_texture
from OpenGL.GL import *

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fs42.station_manager import StationManager
from fs42.osd.content_classifier import ContentType, classify_current_content

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
    default_logo_alpha: float = 1.0


class LogoDisplay(object):
    def __init__(self, window, config: LogoDisplayConfig):
        self.config = config
        self.window = window
        self.window_width, self.window_height = glfw.get_framebuffer_size(window)
        self.station_manager = StationManager()

        self.current_logo_textures: list[int] = []
        self.current_logo_size: tuple[int, int] = (0, 0)
        self.current_frame_durations: list[float] = []
        self.current_frame_index: int = 0
        self.frame_timer: float = 0.0
        self.is_animated: bool = False

        self.current_channel_info: dict = {}
        self.channel_config: dict = {}
        self.time_since_change: float = float("inf")
        self.current_content_type: ContentType = ContentType.UNKNOWN
        self.available_logos: list[Path] = []
        self.current_logo_path: str | None = None
        self.is_displaying_osd_default_logo: bool = False

        self.main_config: dict | None = None

        self.check_status()

    # -------------------------------------------------------------------------
    # Helpers to load logos and config
    # -------------------------------------------------------------------------

    def get_available_logos(self, dir_path: Path) -> list[Path]:
        extensions = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp"]
        found: list[str] = []
        for ext in extensions:
            found.extend(glob.glob(str(dir_path / ext)))
            found.extend(glob.glob(str(dir_path / ext.upper())))
        return [Path(p) for p in found]

    def load_main_config(self) -> dict:
        """
        Load main_config.json from confs/, where FS42 keeps all config files.
        """
        if self.main_config is not None:
            return self.main_config

        cfg_path = project_root / "confs" / "main_config.json"

        try:
            with open(cfg_path, "r") as f:
                self.main_config = json.load(f)
        except Exception:
            self.main_config = {}

        return self.main_config


    # -------------------------------------------------------------------------
    # Tag-based content directory: logo_dir/<first_tag>/
    #    - tags derived from the station's schedule (day/hour-based)
    # -------------------------------------------------------------------------

    def find_content_logo_dir(self, base_dir: Path, station_data: dict) -> Path | None:
        """
        Use the station's schedule to determine the active tag, and
        map that tag to a subdirectory under base_dir.
        """
        now = datetime.datetime.now()
        day_key = now.strftime("%A").lower()  # "monday", "tuesday", etc.
        day_schedule = station_data.get(day_key)

        if not isinstance(day_schedule, dict):
            return None

        # Try exact hour match first
        hour_str = str(now.hour)
        slot = day_schedule.get(hour_str)

        # Optional fallback: latest hour <= now.hour
        if slot is None:
            try:
                sorted_hours = sorted(
                    (int(h) for h in day_schedule.keys() if h.isdigit())
                )
                eligible = [h for h in sorted_hours if h <= now.hour]
                if eligible:
                    best_hour = str(eligible[-1])
                    slot = day_schedule.get(best_hour)
            except Exception:
                slot = None

        if not isinstance(slot, dict):
            return None

        val = slot.get("tags") or slot.get("tag")
        if not val:
            return None

        # Support either a single string or a list/tuple of tags
        if isinstance(val, str):
            first_tag = val
        elif isinstance(val, (list, tuple)) and val:
            first_tag = str(val[0])
        else:
            return None

        safe = (
            first_tag.strip()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
        )
        candidate = base_dir / safe
        if candidate.exists() and candidate.is_dir():
            return candidate
        return None

    # -------------------------------------------------------------------------
    # Month-based temporal directory: logo_dir/<Month>/ or ranges
    # -------------------------------------------------------------------------

    def find_temporal_logo_dir(self, base_dir: Path) -> Path | None:
        today = datetime.date.today()
        month_name = today.strftime("%B")
        day = today.day

        if not base_dir.exists():
            return None

        for sub in base_dir.iterdir():
            if not sub.is_dir():
                continue

            name = sub.name

            # Exact month match, e.g. "October"
            if name == month_name:
                return sub

            # Month range: "October 1 - October 31"
            parts = name.split(" - ")
            if len(parts) == 2:
                left, right = parts
                lp = left.split()
                rp = right.split()
                if len(lp) == 2 and len(rp) == 2:
                    m1, d1s = lp
                    m2, d2s = rp
                    if m1 == m2 == month_name:
                        try:
                            d1 = int(d1s)
                            d2 = int(d2s)
                            if d1 <= day <= d2:
                                return sub
                        except ValueError:
                            pass

        return None

    # -------------------------------------------------------------------------
    # Day-part detection from main_config.json (start_hour / end_hour)
    # -------------------------------------------------------------------------

    def get_current_day_part(self) -> str | None:
        """
        Determine the current day_part from main_config.json.

        Expected shape:

            "day_parts": {
                "morning":  { "start_hour": 6,  "end_hour": 10 },
                "daytime":  { "start_hour": 10, "end_hour": 17 },
                "prime":    { "start_hour": 17, "end_hour": 21 },
                "late":     { "start_hour": 21, "end_hour": 2 },
                "overnight":{ "start_hour": 2,  "end_hour": 6 }
            }

        Wrap-around parts (e.g. 21 → 2) are supported.
        """
        cfg = self.load_main_config()
        day_parts = cfg.get("day_parts")
        if not day_parts or not isinstance(day_parts, dict):
            return None

        now = datetime.datetime.now()
        now_hour = now.hour

        for name, spec in day_parts.items():
            if not isinstance(spec, dict):
                continue
            start = spec.get("start_hour")
            end = spec.get("end_hour")
            if start is None or end is None:
                continue

            # Same-day range (e.g., 6 → 10)
            if start <= end:
                if start <= now_hour < end:
                    return name
            else:
                # Wrap past midnight (e.g., 21 → 2)
                if now_hour >= start or now_hour < end:
                    return name

        return None

    # -------------------------------------------------------------------------
    # Weekday helper: "Monday", "Tuesday", etc.
    # -------------------------------------------------------------------------

    def get_current_weekday(self) -> str:
        """
        Return current weekday name, e.g. "Friday".
        """
        today = datetime.date.today()
        return today.strftime("%A")

    # -------------------------------------------------------------------------
    # Logo selection logic with full hierarchy
    # -------------------------------------------------------------------------

    def select_logo_for_channel(self, station_data: dict) -> Path | None:
        """
        Selection hierarchy:

            1. Tag-based folder:           logo_dir/<first_tag>/
            2. Month + Weekday + daypart:  logo_dir/<Month>/<Weekday>/<day_part>/
            3. Month + Weekday:            logo_dir/<Month>/<Weekday>/
            4. Month + daypart:            logo_dir/<Month>/<day_part>/
            5. Month-only:                 logo_dir/<Month>/ or month-range
            6. Weekday + daypart:          logo_dir/<Weekday>/<day_part>/
            7. Weekday-only:               logo_dir/<Weekday>/
            8. daypart-only:               logo_dir/<day_part>/
            9. Base directory              (original FS42 behavior)
        """
        multi = station_data.get("multi_logo", "single").lower()
        if multi == "off":
            multi = "single"
        elif multi == "random":
            multi = "multi"
        if multi not in ("single", "multi"):
            multi = "single"

        content_dir = station_data.get("content_dir")
        logo_dir = station_data.get("logo_dir")
        default_logo_name = station_data.get("default_logo")

        # Original FS42 semantics: logo_dir relative to content_dir if present,
        # otherwise relative to project_root.
        if content_dir and logo_dir:
            base_dir = Path(content_dir) / logo_dir
        elif logo_dir:
            base_dir = project_root / logo_dir
        else:
            return None

        override_dirs: list[Path] = []

        # 1) Content tag override (derived from the station's schedule)
        cdir = self.find_content_logo_dir(base_dir, station_data)
        if cdir:
            override_dirs.append(cdir)

        # Temporal hints: month, weekday, day_part
        month_dir = self.find_temporal_logo_dir(base_dir)
        day_part_name = self.get_current_day_part()
        weekday_name = self.get_current_weekday()

        # Normalize day_part to filesystem-friendly name
        day_part_folder = None
        if day_part_name:
            day_part_folder = day_part_name.replace(" ", "_")

        # Helper to add a candidate directory if it exists and isn't already listed
        def add_candidate(path: Path):
            if path and path.exists() and path.is_dir():
                if path not in override_dirs:
                    override_dirs.append(path)

        # 2) Month-based combinations first (most specific → less specific)
        if month_dir:
            # Month / Weekday / day_part
            if weekday_name and day_part_folder:
                add_candidate(month_dir / weekday_name / day_part_folder)

            # Month / Weekday
            if weekday_name:
                add_candidate(month_dir / weekday_name)

            # Month / day_part
            if day_part_folder:
                add_candidate(month_dir / day_part_folder)

            # Month-only
            add_candidate(month_dir)
        else:
            # 3) Only use generic weekday/day_part when month_dir is not present
            # Weekday / day_part
            if weekday_name and day_part_folder:
                add_candidate(base_dir / weekday_name / day_part_folder)

            # Weekday-only
            if weekday_name:
                add_candidate(base_dir / weekday_name)

            # day_part-only
            if day_part_folder:
                add_candidate(base_dir / day_part_folder)

        def pick_single() -> Path | None:
            # Try override dirs in order
            for d in override_dirs:
                logos = self.get_available_logos(d)
                if logos:
                    if default_logo_name:
                        cand = d / default_logo_name
                        if cand.exists():
                            return cand
                    return random.choice(logos)

            # Fallback: default_logo in base_dir if defined
            if default_logo_name:
                cand = base_dir / default_logo_name
                if cand.exists():
                    return cand

            # Fallback: any logo in base_dir
            logos = self.get_available_logos(base_dir)
            if logos:
                return random.choice(logos)

            return None

        def pick_multi() -> Path | None:
            pool: list[Path] = []
            for d in override_dirs:
                pool.extend(self.get_available_logos(d))
            if pool:
                self.available_logos = pool
                return random.choice(pool)

            logos = self.get_available_logos(base_dir)
            if logos:
                self.available_logos = logos
                return random.choice(logos)

            return None

        return pick_single() if multi == "single" else pick_multi()

    # -------------------------------------------------------------------------
    # Status reading and content tracking
    # -------------------------------------------------------------------------

    def check_status(self, socket_file: str = SOCKET_FILE) -> None:
        try:
            with open(socket_file, "r") as f:
                status = json.loads(f.read())

            curr_net = self.current_channel_info.get("network_name")
            curr_title = self.current_channel_info.get("title")
            new_net = status.get("network_name")
            new_title = status.get("title")

            if new_net != curr_net:
                self.current_channel_info = status
                self.time_since_change = 0.0
                self.available_logos = []
                self.load_logo_for_channel(status)
                self.current_content_type = classify_current_content()

            elif new_title != curr_title:
                old_type = self.current_content_type
                self.current_content_type = classify_current_content()
                if (
                    old_type != ContentType.FEATURE
                    and self.current_content_type == ContentType.FEATURE
                ):
                    self.time_since_change = 0.0
                    if self.channel_config.get("multi_logo", "single").lower() in (
                        "multi",
                        "random",
                    ):
                        self.load_logo_for_channel(status)
                self.current_channel_info = status

            else:
                self.current_channel_info = status

        except Exception as e:
            print(f"Unable to parse player status for logo: {e}")

    # -------------------------------------------------------------------------
    # Logo loading
    # -------------------------------------------------------------------------

    def load_animated_gif(self, path: str) -> bool:
        try:
            from PIL import Image

            self.clear_logo_textures()
            with Image.open(path) as img:
                frames: list[int] = []
                durations: list[float] = []
                width, height = img.size

                for i in range(img.n_frames):
                    img.seek(i)
                    frame = img.convert("RGBA")
                    duration = max(img.info.get("duration", 100) / 1000.0, 0.01)
                    data = frame.tobytes()
                    fw, fh = frame.size

                    tex = glGenTextures(1)
                    glBindTexture(GL_TEXTURE_2D, tex)
                    glTexImage2D(
                        GL_TEXTURE_2D,
                        0,
                        GL_RGBA,
                        fw,
                        fh,
                        0,
                        GL_RGBA,
                        GL_UNSIGNED_BYTE,
                        data,
                    )
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

                    frames.append(tex)
                    durations.append(duration)

                self.current_logo_textures = frames
                self.current_frame_durations = durations
                self.current_logo_size = (width, height)
                self.current_frame_index = 0
                self.frame_timer = 0.0
                self.is_animated = len(frames) > 1

                print(f"[INFO] Loaded animated logo: {path}")
                return True

        except Exception as e:
            print(f"[ERROR] Error loading animated logo {path}: {e}")
            self.clear_logo_textures()
            return False

    def clear_logo_textures(self) -> None:
        if self.current_logo_textures:
            glDeleteTextures(self.current_logo_textures)
        self.current_logo_textures = []
        self.current_logo_path = None
        self.current_frame_durations = []
        self.current_frame_index = 0
        self.frame_timer = 0.0
        self.is_animated = False

    def load_static_logo(self, path: str) -> None:
        self.clear_logo_textures()
        try:
            tex, w, h = load_texture(path)
            self.current_logo_textures = [tex]
            self.current_frame_durations = [0.0]
            self.current_logo_size = (w, h)
            self.current_frame_index = 0
            self.frame_timer = 0.0
            self.is_animated = False
            print(f"[INFO] Loaded static logo: {path}")
        except Exception as e:
            print(f"[ERROR] Error loading static logo {path}: {e}")
            self.clear_logo_textures()

    def load_logo_for_channel(self, info: dict) -> None:
        logo_path: Path | None = None
        self.channel_config = {}
        self.is_displaying_osd_default_logo = False

        net = info.get("network_name")
        show_logo = True

        if net:
            try:
                station = self.station_manager.station_by_name(net)
                if isinstance(station, dict):
                    self.channel_config = station

                    if station.get("show_logo", True) is False:
                        show_logo = False
                        self.clear_logo_textures()
                        return

                    selected = self.select_logo_for_channel(station)
                    if selected is not None:
                        logo_path = selected
                else:
                    print(f"[WARNING] No station data for {net}")
            except Exception as e:
                print(f"[ERROR] Failed to get station data for {net}: {e}")

        if not logo_path and show_logo:
            if self.config.default_show_logo and self.config.default_logo:
                candidate = Path(self.config.default_logo)
                if candidate.exists():
                    logo_path = candidate
                    self.is_displaying_osd_default_logo = True
                else:
                    print(
                        f"[WARNING] OSD default logo not found: {self.config.default_logo}"
                    )

        if logo_path and logo_path.exists():
            if (
                self.current_logo_path == str(logo_path)
                and not (
                    self.channel_config.get("multi_logo", "single").lower()
                    in ("multi", "random")
                    and not self.is_displaying_osd_default_logo
                )
            ):
                return

            self.current_logo_path = str(logo_path)
            if str(logo_path).lower().endswith(".gif"):
                if not self.load_animated_gif(str(logo_path)):
                    self.load_static_logo(str(logo_path))
            else:
                self.load_static_logo(str(logo_path))
        else:
            self.clear_logo_textures()
            self.is_displaying_osd_default_logo = False

    # -------------------------------------------------------------------------
    # Update & Draw
    # -------------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.time_since_change += dt
        self.check_status()

        if self.is_animated and self.current_logo_textures:
            self.frame_timer += dt
            dur = self.current_frame_durations[self.current_frame_index]
            if dur <= 0.0:
                dur = 0.1
            if self.frame_timer >= dur:
                self.frame_timer -= dur
                self.current_frame_index = (
                    self.current_frame_index + 1
                ) % len(self.current_logo_textures)

    def draw(self) -> None:
        if (
            not self.current_logo_textures
            or self.current_frame_index >= len(self.current_logo_textures)
        ):
            return

        if self.current_content_type != ContentType.FEATURE:
            return

        if self.is_displaying_osd_default_logo:
            permanent = self.config.default_logo_permanent
        else:
            permanent = self.channel_config.get("logo_permanent", False)

        display_time = (
            float(self.channel_config.get("logo_display_time"))
            if not self.is_displaying_osd_default_logo
            and self.channel_config.get("logo_display_time") is not None
            else self.config.display_time
        )

        if (
            not permanent
            and not self.config.always_show
            and self.time_since_change >= display_time
        ):
            return

        width = float(self.channel_config.get("logo_width", self.config.width))
        height = float(self.channel_config.get("logo_height", self.config.height))

        x_margin = float(self.channel_config.get("logo_x_margin", self.config.x_margin))
        y_margin = float(self.channel_config.get("logo_y_margin", self.config.y_margin))

        halign_str = self.channel_config.get("logo_halign", self.config.halign.value)
        valign_str = self.channel_config.get("logo_valign", self.config.valign.value)

        try:
            halign = HAlignment[halign_str.upper()]
        except Exception:
            halign = self.config.halign

        try:
            valign = VAlignment[valign_str.upper()]
        except Exception:
            valign = self.config.valign

        w = width * 2.0
        h = height * 2.0

        if halign == HAlignment.LEFT:
            x = -1.0 + x_margin
        elif halign == HAlignment.RIGHT:
            x = 1.0 - w - x_margin
        else:
            x = -w / 2.0

        if valign == VAlignment.BOTTOM:
            y = -1.0 + y_margin
        elif valign == VAlignment.TOP:
            y = 1.0 - h - y_margin
        else:
            y = -h / 2.0

        tex = self.current_logo_textures[self.current_frame_index]
        glBindTexture(GL_TEXTURE_2D, tex)
        self.draw_logo_quad(x, y, w, h)

    def draw_logo_quad(self, x: float, y: float, w: float, h: float) -> None:
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        alpha = (
            self.config.default_logo_alpha
            if self.is_displaying_osd_default_logo
            else float(
                self.channel_config.get("logo_alpha", self.config.default_logo_alpha)
            )
        )

        glColor4f(1.0, 1.0, 1.0, alpha)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(x, y)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(x + w, y)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(x + w, y + h)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(x, y + h)
        glEnd()

    def __del__(self) -> None:
        if hasattr(self, "current_logo_textures") and self.current_logo_textures:
            glDeleteTextures(self.current_logo_textures)
