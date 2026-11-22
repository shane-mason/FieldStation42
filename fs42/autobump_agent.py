import random
import sys
import os
import subprocess
import datetime
import calendar
import logging
import re
from pathlib import Path
from datetime import date, datetime

sys.path.append(os.getcwd())
from fs42.catalog_entry import CatalogEntry
from fs42.slot_reader import SlotReader
import urllib.parse


class AutoBumpAgent:
    url_prefix = ":autobump:="
    tag_str = ":autobump:"
    _bg_video_durations = {}
    _l = logging.getLogger("AUTOBUMP")
    
    @staticmethod
    def static_url(path):
        from fs42.station_manager import StationManager
        return f"{StationManager().local_server_url()}/static/{path}"

    @staticmethod
    def day_parts():
        from fs42.station_manager import StationManager

        try:
            return StationManager().get_day_parts()
        except KeyError:
            return {}

    @staticmethod
    def bump_page_url():
        return AutoBumpAgent.static_url("bump/bump.html")

    @staticmethod
    def do_fill(station_config):
        if "autobump" not in station_config:
            return False
        if "fill_break" not in station_config["autobump"]:
            return False
        if random.random() < station_config["autobump"]["fill_break"]:
            return True
        return False

    @staticmethod
    def fill_block(station_config, duration, scheduled_time=None):
        if "autobump" in station_config:
            ab_config = dict(station_config["autobump"])
        elif "off_air_autobump" in station_config:
            ab_config = dict(station_config["off_air_autobump"])
        else:
            return None

        ab_config = AutoBumpAgent.resolve_bg_media_config(ab_config, scheduled_time)
        ab_config["duration"] = duration
        fill_bump = AutoBumpAgent.next_up_bump(ab_config, AutoBumpAgent.bump_page_url(), station_config["network_name"], False, True, scheduled_time)
        return fill_bump


    @staticmethod
    def gen_bumps(station_config, scheduled_time=None):
        if "autobump" not in station_config:
            return {"start_block": None, "end_block": None}

        ab_config = dict(station_config["autobump"])
        ab_config = AutoBumpAgent.resolve_bg_media_config(ab_config, scheduled_time)
        # first, check duration:
        # if the user set a duration, respect that as the bump length
        # otherwise, video-backed autobumps can use the video length as a default
        if "duration" not in ab_config or not ab_config["duration"]:
            if "bg_video" in ab_config and ab_config["bg_video"]:
                video_duration = AutoBumpAgent.get_bg_video_duration(ab_config["bg_video"])
                loop_count = AutoBumpAgent.get_bg_video_loop_count(ab_config)

                if video_duration:
                    ab_config["duration"] = video_duration * loop_count
                else:
                    ab_config["duration"] = 7
            else:
                ab_config["duration"] = 7

        msg_bump = AutoBumpAgent.message_bump(ab_config, AutoBumpAgent.bump_page_url(), scheduled_time=scheduled_time)
        next_bump = AutoBumpAgent.next_up_bump(ab_config, AutoBumpAgent.bump_page_url(), station_config["network_name"], scheduled_time=scheduled_time)
        return {"message_bump": msg_bump, "next_bump": next_bump}

    @staticmethod
    def is_autobump_url(url):
        return url.startswith(AutoBumpAgent.url_prefix)

    @staticmethod
    def extract_url(prefixed_url):
        return prefixed_url.removeprefix(AutoBumpAgent.url_prefix)

    @staticmethod
    def message_bump(ab_config, base_url, loopmusic=True, show_countdown=False, scheduled_time=None):
        ab_config = dict(ab_config)
        ab_config["loopmusic"] = "true" if loopmusic else "false"
        ab_config["countdown"] = "true" if show_countdown else "false"
        if "next_network" in ab_config:
            del ab_config["next_network"]
        message_qs = AutoBumpAgent.generate_bump_query(ab_config, scheduled_time)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], AutoBumpAgent.tag_str)
        return block

    @staticmethod
    def next_up_bump(ab_config, base_url, network_name, loopmusic=True, show_countdown=False, scheduled_time=None):
        ab_config = dict(ab_config)
        ab_config["subtitle"] = f"Coming up on {network_name}"
        ab_config["next_network"] = network_name
        ab_config["loopmusic"] = "true" if loopmusic else "false"
        ab_config["countdown"] = "true" if show_countdown else "false"
        message_qs = AutoBumpAgent.generate_bump_query(ab_config, scheduled_time)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], AutoBumpAgent.tag_str)
        return block

    @staticmethod
    def get_bg_media_extensions(media_type):
        extensions = {
            "video": {".webm"},
            "music": {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".aac"},
            "css": {".css"}
        }
        return extensions[media_type]

    @staticmethod
    def get_bg_media_root():
        return (
            Path("fs42")
            / "fs42_server"
            / "static"
            / "bump"
        )

    @staticmethod
    def resolve_bg_media_directory(directory):
        directory = Path(directory)

        # Absolute paths and paths relative to the working directory
        if directory.is_dir():
            return directory

        # Paths relative to the appropriate static media directory
        directory = AutoBumpAgent.get_bg_media_root() / directory

        if directory.is_dir():
            return directory

        return None

    @staticmethod
    def get_temporal_date_match(name, today):
        # Month filename or directory, e.g. January
        if name.lower() == today.strftime("%B").lower():
            return (2, 0)

        # Exact date or date range
        current_datetime = datetime.combine(today, datetime.min.time())

        if not SlotReader._date_key_matches(name, current_datetime):
            return None

        # Exact date, e.g. April 23
        if " - " not in name:
            return (0, 0)

        # Calculate date-range width 
        try:
            parts = [part.strip() for part in name.split(" - ")]

            start = datetime.strptime(
                f"{today.year} {parts[0]}", "%Y %B %d"
            ).date()

            end = datetime.strptime(
                f"{today.year} {parts[1]}", "%Y %B %d"
            ).date()

            if start <= end:
                width = (end - start).days
            else:
                year_end = date(today.year, 12, 31)
                year_start = date(today.year, 1, 1)

                width = (
                    (year_end - start).days
                    + (end - year_start).days
                    + 1
                )

            month_days = calendar.monthrange(today.year, today.month)[1]

            # Shorter ranges override the monthly style.
            # Equal or longer ranges defer to the month.
            if width < month_days:
                return (1, width)
            else:
                return (3, width)
                
        except ValueError:
            return None

    @staticmethod
    def is_matching_daypart(name, day_parts, now):

        name = name.lower()
        hour = now.hour
        
        # Named daypart
        if name in day_parts:
            definition = day_parts[name]

            if isinstance(definition, range):
                # Support ranges that cross midnight, e.g. range(23, 26).
                return hour in definition or (hour + 24) in definition

            if isinstance(definition, (list, tuple)):
                return hour in definition or (hour + 24) in definition

            if isinstance(definition, dict):
                start = definition["start_hour"]
                end = definition["end_hour"]
            else:
                return False

        else:
            # Numeric range, e.g. 18-23 or 23-2
            match = re.fullmatch(
                r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*",
                name
            )

            if not match:
                return False

            start, end = map(int, match.groups())

            if start > 23 or end > 23:
                return False


        if start < end:
            return start <= hour < end

        return hour >= start or hour < end

    @staticmethod
    def select_from_temporal_directory(directory, media_type, day_parts, now):
        # First look for matching daypart files.
        daypart_files = [
            path for path in AutoBumpAgent.get_bg_media_files(
                directory, media_type
            )
            if AutoBumpAgent.is_matching_daypart(
                path.stem, day_parts, now
            )
        ]

        if daypart_files:
            AutoBumpAgent._l.debug(
                "Found matching %s daypart files in %s: %s",
                media_type,
                directory,
                [path.name for path in daypart_files]
            )
            # Prefer named dayparts over equivalent numeric ranges.
            named = [
                path for path in daypart_files
                if path.stem.lower() in day_parts
            ]

            return str(random.choice(named or daypart_files))

        # also support nested daypart folders.
        daypart_dirs = [
            path for path in directory.iterdir()
            if path.is_dir()
            and AutoBumpAgent.is_matching_daypart(
                path.name, day_parts, now
            )
        ]

        if daypart_dirs:
            AutoBumpAgent._l.debug(
                "Found matching %s daypart directories in %s: %s",
                media_type,
                directory,
                [path.name for path in daypart_dirs]
            )
            named = [
                path for path in daypart_dirs
                if path.name.lower() in day_parts
            ]

            selected_dir = random.choice(named or daypart_dirs)

            candidates = AutoBumpAgent.get_bg_media_files(
                selected_dir, media_type
            )

            if candidates:
                return str(random.choice(candidates))

        return None

    @staticmethod
    def select_temporal_override(
        base_dir,
        media_type,
        allow_root_random=True,
        scheduled_time=None
    ):
        AutoBumpAgent._l.debug(
            "Searching for %s temporal overrides in %s",
            media_type,
            base_dir
        )
        if not base_dir.is_dir():
            return None

        now=scheduled_time
        today = now.date()

        day_parts = AutoBumpAgent.day_parts()

        default_day_parts = {
            "morning": {"start_hour": 6, "end_hour": 10},
            "daytime": {"start_hour": 10, "end_hour": 18},
            "prime": {"start_hour": 18, "end_hour": 23},
            "late": {"start_hour": 23, "end_hour": 2},
            "overnight": {"start_hour": 2, "end_hour": 6}
        }

        day_parts = {
            **default_day_parts,
            **day_parts
        }

        AutoBumpAgent._l.debug(
            "Checking %s temporal overrides in %s; current time: %s",
            media_type,
            base_dir,
            scheduled_time.strftime("%Y-%m-%d %H:%M")
        )

        date_matches = []

        # Find date-specific files and directories.
        for path in base_dir.iterdir():
            if path.is_file():
                if path.suffix.lower() not in AutoBumpAgent.get_bg_media_extensions(media_type):
                    continue

                name = path.stem

            elif path.is_dir():
                name = path.name

            else:
                continue

            match = AutoBumpAgent.get_temporal_date_match(
                name, today
            )

            if match is not None:
                date_matches.append((match, path))

        # Most specific date match first.
        date_matches.sort(key=lambda item: item[0])

        AutoBumpAgent._l.debug(
            "Temporal date matches for %s: %s",
            media_type,
            [path.name for _, path in date_matches]
        )

        # First, check all date matches for exact files and daypart matches.
        for _, path in date_matches:
            if path.is_file():
                AutoBumpAgent._l.debug(
                    "Selected %s date override: %s",
                    media_type,
                    path
                )
                return str(path)

            selected = AutoBumpAgent.select_from_temporal_directory(
                path,
                media_type,
                day_parts,
                now
            )

            if selected:
                AutoBumpAgent._l.debug(
                    "Selected %s temporal override: %s (from %s)",
                    media_type,
                    selected,
                    path.name
                )
                return selected

        # No date-specific daypart match, try random media from matching
        # date directories before considering root-level media.
        for _, path in date_matches:
            if path.is_dir():
                candidates = AutoBumpAgent.get_bg_media_files(
                    path, media_type
                )

                if candidates:
                    selected = random.choice(candidates)

                    AutoBumpAgent._l.debug(
                        "Selected random %s media from date directory: %s",
                        media_type,
                        selected
                    )
                    return str(selected)

        # Look for daypart-specific files or directories
        root_daypart_files = [
            path for path in AutoBumpAgent.get_bg_media_files(
                base_dir, media_type
            )
            if AutoBumpAgent.is_matching_daypart(
                path.stem, day_parts, now
            )
        ]

        if root_daypart_files:
            named = [
                path for path in root_daypart_files
                if path.stem.lower() in day_parts
            ]

            selected = random.choice(named or root_daypart_files)
            AutoBumpAgent._l.debug(
                "Selected %s daypart override: %s",
                media_type,
                selected
            )
            return str(selected)
            
        root_daypart_dirs = [
            path for path in base_dir.iterdir()
            if path.is_dir()
            and AutoBumpAgent.is_matching_daypart(
                path.name, day_parts, now
            )
        ]

        if root_daypart_dirs:
            named = [
                path for path in root_daypart_dirs
                if path.name.lower() in day_parts
            ]

            selected_dir = random.choice(named or root_daypart_dirs)

            candidates = AutoBumpAgent.get_bg_media_files(
                selected_dir, media_type
            )

            if candidates:
                selected = random.choice(candidates)

                AutoBumpAgent._l.debug(
                    "Selected random root-level %s media: %s",
                    media_type,
                    selected
                )

                return str(selected)

        # Choose a random root-level file, excluding date and daypart overrides.
        if allow_root_random:
            candidates = [
                path for path in AutoBumpAgent.get_bg_media_files(
                    base_dir, media_type
                )
                if AutoBumpAgent.get_temporal_date_match(
                    path.stem, today
                ) is None
                and not AutoBumpAgent.is_matching_daypart(
                    path.stem, day_parts, now
                )
            ]

            if candidates:
                selected = random.choice(candidates)

                AutoBumpAgent._l.debug(
                    "Selected random root-level %s media: %s",
                    media_type,
                    selected
                )

                return str(selected)

        return None

    @staticmethod
    def get_bg_media_files(directory, media_type):
        extensions = AutoBumpAgent.get_bg_media_extensions(media_type)

        return [
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        ]

    @staticmethod
    def select_bg_media(value, media_type, scheduled_time=None):
        if media_type == "css":
            base_dir = AutoBumpAgent.resolve_bg_media_directory(value)

            if not base_dir:
                AutoBumpAgent._l.warning(
                    "Unable to resolve configured CSS media directory: %s",
                    value
                )
                return value

            selected = AutoBumpAgent.select_temporal_override(
                base_dir,
                "css",
                allow_root_random=False,
                scheduled_time=scheduled_time
            )

            if selected:
                AutoBumpAgent._l.debug(
                    "Selected temporal CSS override: %s (scheduled for %s)",
                    selected,
                    scheduled_time
                )
                return selected

            AutoBumpAgent._l.debug(
                "No temporal CSS override found; using configured CSS: %s",
                value
            )
            return value

        if not value:
            return None

        # External URLs and absolute URL paths are not filesystem paths
        if value.startswith(("http://", "https://", "/")):
            return value

        # Preserve explicitly supplied filesystem paths
        if os.path.isfile(value):
            return value

        # Resolve relative paths against the shared media root
        media_root = AutoBumpAgent.get_bg_media_root()
        media_path = media_root / value

        # Use a configured individual file directly.
        if media_path.is_file():
            return str(media_path)

        # Otherwise, treat the configured value as a directory.
        base_dir = AutoBumpAgent.resolve_bg_media_directory(value)

        if not base_dir:
            AutoBumpAgent._l.warning(
                "Unable to resolve configured %s media directory: %s. Using configured value.",
                media_type,
                value
            )
            return value

        selected = AutoBumpAgent.select_temporal_override(
            base_dir,
            media_type,
            scheduled_time=scheduled_time
        )

        if selected:
            AutoBumpAgent._l.debug(
                "Selected %s media: %s",
                media_type,
                selected
            )
        else:
            AutoBumpAgent._l.warning(
                "No usable %s media found in %s",
                media_type,
                base_dir
            )

        return selected
    
    @staticmethod
    def resolve_bg_media_config(config, scheduled_time=None):
        # Resolve directory-based video and music settings once.
        config = dict(config)

        for key, media_type in (
            ("bg_video", "video"),
            ("bg_music", "music")
        ):
            if config.get(key):
                selected = AutoBumpAgent.select_bg_media(
                    config[key],
                    media_type,
                    scheduled_time
                )

                if selected:
                    config[key] = selected
                else:
                    AutoBumpAgent._l.debug(
                        "Unable to resolve configured %s media: %s; removing from autobump configuration",
                        media_type,
                        config[key]
                    )
                    config.pop(key, None)

        return config

    @staticmethod
    def resolve_bg_media_url(value, media_type):
        value = str(value)

        if value.startswith(("http://", "https://", "/")):
            return value

        static_root = (
            Path("fs42") / "fs42_server" / "static"
        ).resolve()

        path = Path(value)

        # Resolve relative paths so paths that already include
        # fs42/fs42_server/static aren't prefixed a second time.
        resolved_path = path.resolve()

        try:
            relative = resolved_path.relative_to(static_root)
            return AutoBumpAgent.static_url(relative.as_posix())
        except ValueError:
            pass

        # A filename rather than a full path, use normal media directory.
        if not path.is_absolute():
            return AutoBumpAgent.static_url(
                f"bump/{value}"
            )

        return value

    @staticmethod
    def get_bg_video_loop_count(config):
        try:
            loop_count = int(config.get("bg_video_loop_count", 1))
            return max(loop_count, 1)
        except Exception:
            return 1

    @staticmethod
    def get_bg_video_duration(bg_video):
        if bg_video not in AutoBumpAgent._bg_video_durations:
            AutoBumpAgent._bg_video_durations[bg_video] = AutoBumpAgent._probe_bg_video_duration(bg_video)
        return AutoBumpAgent._bg_video_durations[bg_video]

    @staticmethod
    def _probe_bg_video_duration(bg_video):
        if str(bg_video).startswith("http"):
            return None

        video_path = AutoBumpAgent.resolve_bg_video_path(bg_video)

        if not video_path or not os.path.exists(video_path):
            return None

        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            duration = float(result.stdout.strip())
            return duration if duration > 0 else None
        except Exception:
            return None

    @staticmethod
    def resolve_bg_video_path(bg_video):
        # full paths can be probed directly
        if os.path.isabs(str(bg_video)):
            return bg_video

        # try the configured value relative to the current working directory
        if os.path.exists(bg_video):
            return bg_video

        # bare filenames served from static/bump
        video_path = os.path.join("fs42", "fs42_server", "static", "bump", str(bg_video))
        if os.path.exists(video_path):
            return video_path

        # legacy support:
        # bare filenames served from static/bump/video, similar to bg_music
        video_path = os.path.join("fs42", "fs42_server", "static", "bump", "video", str(bg_video))
        if os.path.exists(video_path):
            return video_path

        return None

    @staticmethod
    def resolve_bg_video_url(bg_video):
        if str(bg_video).startswith("http"):
            return bg_video

        # absolute URLs served from this FS42 instance can pass through
        if str(bg_video).startswith("/"):
            return bg_video

        # legacy filenames are served from static/bump/video
        legacy_video_path = os.path.join("fs42", "fs42_server", "static", "bump", "video", str(bg_video))

        if os.path.exists(legacy_video_path):
            return AutoBumpAgent.static_url(f"bump/video/{bg_video}")

        # bare filenames are served from static/bump
        return AutoBumpAgent.static_url(f"bump/{bg_video}")

    @staticmethod
    def generate_bump_query(config: dict, scheduled_time=None) -> str:
        """
        Generate a query string for bump.html with the specified parameters.

        Args:
            config: Dictionary containing bump configuration
                - title (required): Main station name/title
                - subtitle: Station tagline or description
                - variation: Visual style ('modern', 'retro', 'corporate', 'terminal')
                - detail1, detail2, detail3: Custom detail lines
                - bg_color: Background color (hex format, e.g., '#ff0000')
                - fg_color: Text color (hex format, e.g., '#ffffff')
                - bg: Background image URL
                - bg_video: Background video URL or filename
                - bg_video_loop_count: Number of times to play the background video if no duration is set
                - bg_video_audio: Whether to use background video audio when bg_music is not set
                - text_position: Position of text overlay
                - text_delay: Delay before text appears, in seconds
                - text_fade_in: Text fade-in duration, in seconds
                - text_fade_out: Text fade-out duration, in seconds
                - text_hide_before_end: How many seconds before the autobump ends that text should be fully hidden
                - css: URL to custom CSS override file
                - next_network: Network name to fetch next 3 upcoming shows
                - duration: Auto-hide after specified milliseconds (0 = no auto-hide)
                - bg_music: Background music URL or filename (e.g., 'retro.mp3' or full URL)

        Returns:
            Query string for bump.html
        """
        config = AutoBumpAgent.resolve_bg_media_config(config, scheduled_time)
        if "title" not in config:
            raise ValueError("title is required")

        params = {}
        # Always check for a temporal CSS override, even when
        # the channel configuration doesn't explicitly specify CSS.
        css_value = AutoBumpAgent.select_bg_media(
            config.get("css"),
            "css",
            scheduled_time
        )

        if css_value:
            params["css"] = AutoBumpAgent.resolve_bg_media_url(
                css_value,
                "css"
            )
            
        # Map dictionary keys to URL parameter names
        key_mapping = {
            "title": "title",
            "subtitle": "subtitle",
            "variation": "variation",
            "detail1": "detail1",
            "detail2": "detail2",
            "detail3": "detail3",
            "bg_color": "bg_color",
            "fg_color": "fg_color",
            "bg": "bg",
            "bg_video": "bg_video",
            "bg_video_loop_count": "bg_video_loop_count",
            "bg_video_audio": "bg_video_audio",
            "text_position": "text_position",
            "text_delay": "text_delay",
            "text_fade_in": "text_fade_in",
            "text_fade_out": "text_fade_out",
            "text_hide_before_end": "text_hide_before_end",
            "next_network": "next_network",
            "duration": "duration",
            "bg_music": "bg_music",
            "loopmusic": "loopmusic",
            "countdown": "countdown"
        }

        # Process each config item
        for key, url_param in key_mapping.items():
            if key in config and config[key] is not None:
                value = config[key]
                if key == "duration":
                    value = str(value*1000)
                elif key == "bg_music":
                    # Convert filename to full URL if not already a URL
                    value = AutoBumpAgent.resolve_bg_media_url(value, "music")
                elif key == "bg_video":
                    value = AutoBumpAgent.resolve_bg_media_url(value, "video")
                elif key == "bg_video_audio":
                    value = str(value).lower()
                params[url_param] = value

        # Generate query string
        return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def main():
    """Test the generate_bump_query method with various configurations."""

    # Test basic configuration
    basic_config = {"title": "FSTV", "subtitle": "Field Station Television"}
    print("Basic config:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(basic_config)}")
    print()

    # Test retro variation with programming
    retro_config = {
        "title": "FSTV",
        "subtitle": "Field Station Television",
        "variation": "retro",
        "next_network": "Sitcomx",
        "duration": 10000,
    }
    print("Retro with programming:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(retro_config)}")
    print()

    # Test video background with explicit duration
    # this protects users from very long videos creating very long autobumps
    video_config = {
        "title": "FSTV",
        "subtitle": "Field Station Television",
        "variation": "retro",
        "bg_video": "example.webm",
        "bg_video_loop_count": 2,
        "bg_video_audio": True,
        "text_position": "right",
        "text_delay": 1.5,
        "text_fade_in": 0.75,
        "text_fade_out": 0.5,
        "text_hide_before_end": 3,
        "duration": 12
    }
    print("Video background:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(video_config)}")
    print()

    # Test complete configuration
    complete_config = {
        "title": "TESTTV",
        "subtitle": "Test Broadcasting Network",
        "variation": "modern",
        "detail1": "Channel 42",
        "detail2": "testtv.com",
        "detail3": "24/7 Testing",
        "bg_color": "#ff0000",
        "fg_color": "#ffffff",
        "next_network": "Sitcomx",
        "duration": 15000
    }
    print("Complete configuration:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(complete_config)}")
    print()

    station_config = {"autobump": complete_config, "network_name": "Sitcomx"}

    print(AutoBumpAgent.message_bump(retro_config, AutoBumpAgent.bump_page_url(),scheduled_time=scheduled_time))
    print(AutoBumpAgent.next_up_bump(retro_config, AutoBumpAgent.bump_page_url(), "Sitcomx",scheduled_time=scheduled_time))
    gen_bumps = AutoBumpAgent.gen_bumps(station_config,scheduled_time=scheduled_time)
    print(gen_bumps)
    print(gen_bumps.get("message_bump", "NONE"))
    print(gen_bumps.get("next_bump", "NONE"))


if __name__ == "__main__":
    main()
