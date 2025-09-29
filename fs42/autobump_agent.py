import sys
import os

sys.path.append(os.getcwd())
from fs42.catalog_entry import CatalogEntry
import urllib.parse


class AutoBumpAgent:
    base_url = "http://127.0.0.1:4242/static/bump/bump.html"
    url_prefix = ":autobump:="

    @staticmethod
    def gen_bumps(station_config):
        if "autobump" not in station_config:
            return {"start_block": None, "end_block": None}

        ab_config = station_config["autobump"]

        # first, check duration:
        if "duration" not in ab_config or not ab_config["duration"]:
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
    def message_bump(ab_config, base_url):
        message_qs = AutoBumpAgent.generate_bump_query(ab_config)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], ":autobump:")
        return block

    @staticmethod
    def next_up_bump(ab_config, base_url, network_name):
        ab_config["subtitle"] = f"Coming up on {network_name}"
        ab_config["next_network"] = network_name
        message_qs = AutoBumpAgent.generate_bump_query(ab_config)
        message_url = f"{AutoBumpAgent.url_prefix}{base_url}?{message_qs}"
        block = CatalogEntry(message_url, ab_config["duration"], ":autobump:")
        return block

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
            "css": "css",
            "next_network": "next_network",
            "duration": "duration",
            "bg_music": "bg_music",
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
        "next_network": "fstv",
        "duration": 10000,
    }
    print("Retro with programming:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(retro_config)}")
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
        "next_network": "testtv",
        "duration": 15000,
    }
    print("Complete configuration:")
    print(f"Query: {AutoBumpAgent.generate_bump_query(complete_config)}")
    print()

    station_config = {"autobump": retro_config, "network_name": "FSTV"}

    print(AutoBumpAgent.message_bump(retro_config, "http://test/test.html"))
    print(AutoBumpAgent.next_up_bump(retro_config, "http://test/test.html", "FSTV"))
    gen_bumps = AutoBumpAgent.gen_bumps(station_config)
    print(gen_bumps["start_block"])
    print(gen_bumps["end_block"])


if __name__ == "__main__":
    main()
