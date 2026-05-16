import random
import sys
import os
import subprocess

sys.path.append(os.getcwd())
from fs42.catalog_entry import CatalogEntry
import urllib.parse


class AutoBumpAgent:
    base_url = "http://127.0.0.1:4242/static/bump/bump.html"
    url_prefix = ":autobump:="


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
    def fill_block(station_config, duration):
        if "autobump" not in station_config:
            return None
        ab_config = station_config["autobump"]
        ab_config["duration"] = duration
        fill_bump = AutoBumpAgent.next_up_bump(ab_config, AutoBumpAgent.base_url, station_config["network_name"], False, True)
        return fill_bump


    @staticmethod
    def gen_bumps(station_config):
        if "autobump" not in station_config:
            return {"start_block": None, "end_block": None}

        ab_config = station_config["autobump"]

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

        msg_bump = AutoBumpAgent.message_bump(ab_config, AutoBumpAgent.base_url)
        next_bump = AutoBumpAgent.next_up_bump(ab_config, AutoBumpAgent.base_url, station_config["network_name"])
        return {"message_bump": msg_bump, "next_bump": next_bump}

    @staticmethod
    def is_autobump_url(url):
        return url.startswith(AutoBumpAgent.url_prefix)

    @staticmethod
    def extract_url(prefixed_url):
        return prefixed_url.removeprefix(AutoBumpAgent.url_prefix)

    @staticmethod
    def message_bump(ab_config, base_url, loopmusic=True, show_countdown=False):
        ab_config["loopmusic"] = "true" if loopmusic else "false"
        ab_config["countdown"] = "true" if show_countdown else "false"
        if "next_network" in ab_config:
            del ab_config["next_network"]
        message_qs = AutoBumpAgent.generate_bump_query(ab_config)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], ":autobump:")
        return block

    @staticmethod
    def next_up_bump(ab_config, base_url, network_name, loopmusic=True, show_countdown=False):
        ab_config["subtitle"] = f"Coming up on {network_name}"
        ab_config["next_network"] = network_name
        ab_config["loopmusic"] = "true" if loopmusic else "false"
        ab_config["countdown"] = "true" if show_countdown else "false"
        message_qs = AutoBumpAgent.generate_bump_query(ab_config)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], ":autobump:")
        return block

    @staticmethod
    def get_bg_video_loop_count(config):
        try:
            loop_count = int(config.get("bg_video_loop_count", 1))
            return max(loop_count, 1)
        except Exception:
            return 1

    @staticmethod
    def get_bg_video_duration(bg_video):
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

        # bare filenames are served from static/bump/video, similar to bg_music
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

        # bare filenames are served from static/bump/video
        return f"http://127.0.0.1:4242/static/bump/video/{bg_video}"

    @staticmethod
    def generate_bump_query(config: dict) -> str:
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
        if "title" not in config:
            raise ValueError("title is required")

        params = {}

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
            "css": "css",
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
                    if not str(value).startswith("http"):
                        value = f"http://127.0.0.1:4242/static/bump/music/{value}"
                elif key == "bg_video":
                    value = AutoBumpAgent.resolve_bg_video_url(value)
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

    print(AutoBumpAgent.message_bump(retro_config, AutoBumpAgent.base_url))
    print(AutoBumpAgent.next_up_bump(retro_config, AutoBumpAgent.base_url, "Sitcomx"))
    gen_bumps = AutoBumpAgent.gen_bumps(station_config)
    print(gen_bumps)
    print(gen_bumps.get("message_bump", "NONE"))
    print(gen_bumps.get("next_bump", "NONE"))


if __name__ == "__main__":
    main()
