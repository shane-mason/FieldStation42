import re
from pathlib import Path


DEFAULT_UPPERCASE_WORDS = {
    "FBI", "CIA", "USA", "UK", "NY", "DC", "CSI", "NCIS",
    "SVU", "SWAT", "JAG", "ER", "MASH", "NYPD", "WKRP", "UFO",
    "AI", "GI", "RIPD", "THX", "UHF", "SHIELD", "SEAL", "ALF",
    "RV", "POW", "MIA", "XXX", "DEBS", "PCU", "FUBAR", "TMNT",
    "RRR", "RBG", "JCVD", "WWE", "WWF", "BMX", "CHIPS", "MXC",
    "SAS", "MI5", "CB4", "PK", "LOL", "BFG", "II", "PM"
    "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
    "XIII", "XIV", "XV",
    "NFL", "MLB", "NBA", "NHL", "MLS", "NCAA", "WNBA", "PGA",
    "ATP", "WTA", "UFC", "NASCAR", "FIFA", "UEFA", "F1", "MMA",
    "AHL", "XFL", "CFL", "EPL",
    "NBC", "CBS", "ABC", "PBS", "MTV", "VH1", "TBS", "TNT",
    "TLC", "HBO", "ESPN", "CNN", "CNBC", "MSNBC", "BBC", "ITV",
    "CBC", "QVC", "HSN", "WGN", "KTLA", "TCM", "IFC", "SYFY",
    "AMC", "FX", "CW", "HLN", "WB", "MGM", "PG"
}


class TitleParser:
    @staticmethod
    def _apply_case(word: str, upper_words: set) -> str:
        if word.upper() in upper_words:
            return word.upper()
        return word.capitalize()

    @staticmethod
    def parse_title(in_str: str, custom_patterns: list = None, uppercase_words: list = None) -> str:
        if not in_str:
            return ""  # Consider defaulting to No Information or No Data to match TV Guides

        filename = in_str.strip()

        # Remove file extension
        filename = Path(filename).stem

        # Additions to (not replacements of) the default uppercase word set
        upper_words = DEFAULT_UPPERCASE_WORDS
        if uppercase_words:
            upper_words = upper_words | {w.upper() for w in uppercase_words}

        # Define separator pattern - spaces, dots, underscores, dashes
        sep = r"[\s._-]+"

        # Default built-in patterns
        default_patterns = [
            # Title + separators + "Title" + number suffix (e.g., "Show Name - Title1", "Show Name TITLE2")
            (r"^(.+?)" + sep + r"[tT][iI][tT][lL][eE]\d+$", 1),
            # [Group] Title - Episode (release group prefix)
            (r"^\[.+?\]" + sep + r"(.+?)" + sep + r"\d+.*$", 1),
            # Title (including sequels) + year in parentheses - strip the year
            (r"^(.+?)\s*\(\d{4}\)$", 1),
            # Title + separators + season/episode pattern + optional extra (including duplicate episodes like s01e03e03)
            (r"^(.+?)" + sep + r"(?:[sS]\d+(?:" + sep + r"?[eE]\d+)+|[sS]\d+[eE]\d+(?:[eE]\d+)*|\d+[xX]\d+)(?:" + sep + r".*)?$", 1),
            # Title (Year) + separators + season/episode pattern + separators + episode name + separators + extras
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
            # Title + separators + simple episode number (but only if followed by episode-like content, not years)
            (r"^(.+?)" + sep + r"\d{1,3}(?:" + sep + r"(?!\d{4}(?:\s|$)).+)+$", 1),
            # Just title (fallback)
            (r"^(.+)$", 1),
        ]

        # Prepend custom patterns so they are tried first (higher priority)
        if custom_patterns:
            patterns = custom_patterns + default_patterns
        else:
            patterns = default_patterns

        for pattern, group in patterns:
            match = re.match(pattern, filename)
            if match:
                title = match.group(group)
                # Clean up the title
                title = re.sub(r"[._-]", " ", title)  # Replace dots, dashes and underscores with spaces
                title = re.sub(r"\s+", " ", title)  # Normalize multiple spaces
                title = title.strip()
                # Convert to title case
                return " ".join(TitleParser._apply_case(word, upper_words) for word in title.split())

        # Fallback: return cleaned filename
        cleaned = re.sub(r"[._-]", " ", filename)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return " ".join(TitleParser._apply_case(word, upper_words) for word in cleaned.split())
