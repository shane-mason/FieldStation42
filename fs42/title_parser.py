import re
from pathlib import Path


class TitleParser:
    @staticmethod
    def parse_title(in_str: str) -> str:
        if not in_str:
            return ""  # Consider defaulting to No Information or No Data to match TV Guides

        filename = in_str.strip()

        # Remove file extension
        filename = Path(filename).stem

        # Define separator pattern - spaces, dots, underscores, dashes
        sep = r"[\s._-]+"

        patterns = [
            # [Group] Title - Episode (release group prefix)
            (r"^\[.+?\]" + sep + r"(.+?)" + sep + r"\d+.*$", 1),
            # Title + separators + season/episode pattern + optional extra (including duplicate episodes like s01e03e03)
            (r"^(.+?)" + sep + r"(?:[sS]\d+(?:" + sep + r"?[eE]\d+)+|[sS]\d+[eE]\d+(?:[eE]\d+)*|\d+[xX]\d+)(?:" + sep + r".*)?$", 1),
            # Title (Year) + seperators + season/episode pattern + seperators + episode name + seperators + extras
            (
                r"^(.+?)(?:\s\(\d{4}\))"
                + sep
                + r"(?:[sS]\d+"
                + sep
                + r"?[eE]\d+|[sS]\d+[eE]\d+|\d+[xX]\d+)(?:"
                + sep
                + r".*)?$",
                1,
            ),
            # Title + version/volume format (show_title_V1-0003) - before simple episode
            (r"^(.+?)[\s._-]+V\d+[\s._-]+\d+$", 1),
            # Title + separators + episode indicators + number (e.g., "e2", "ep3", "episode4", "Episode 1")
            (r"^(.+?)" + sep + r"(?:[eE](?:p(?:isode)?)?(?:" + sep + r")?\d+|[eE]\d+)(?:" + sep + r".*)?$", 1),
            # Title + separators + simple episode number (but only if followed by more content like episode title)
            (r"^(.+?)" + sep + r"\d+(?:" + sep + r".+)+$", 1),
            # Just title (fallback)
            (r"^(.+)$", 1),
        ]

        for pattern, group in patterns:
            match = re.match(pattern, filename)
            if match:
                title = match.group(group)
                # Clean up the title
                title = re.sub(r"[._-]", " ", title)  # Replace dots, dashes and underscores with spaces
                title = re.sub(r"\s+", " ", title)  # Normalize multiple spaces
                title = title.strip()
                # Convert to title case
                return " ".join(word.capitalize() for word in title.split())

        # Fallback: return cleaned filename
        cleaned = re.sub(r"[._-]", " ", filename)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return " ".join(word.capitalize() for word in cleaned.split())
