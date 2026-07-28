import re


class TitleParser:
    # Path().stem and os.path.splitext() split at the LAST dot, which eats title
    # text in names like "G.I. Joe" or "C.O.P.S". Callers already strip the
    # extension, so match only real video extensions -- this is idempotent and
    # safe to apply twice.
    VIDEO_EXT = re.compile(
        r"\.(mp4|mkv|avi|mov|m4v|webm|wmv|flv|mpg|mpeg|ts|m2ts|ogv|divx|vob)$", re.I
    )
    # Dotted acronyms: G.I. / C.O.P.S / S.W.A.T.
    ACRONYM = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]\.){2,}[A-Za-z]?(?![A-Za-z0-9])")
    # Single-dot abbreviations the acronym rule is too strict to catch
    ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|St|Jr|Sr|Lt|Sgt|Capt|Prof|Gen|Col)\.", re.I)
    # Hyphen welded between two word chars: He-Man, Spider-Man.
    # Spaced separators (" - ") are untouched by the lookarounds.
    INNER_DASH = re.compile(r"(?<=[A-Za-z0-9])-(?=\s|$)|(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])")
    # Strict Roman numeral form -- rejects words that merely use those letters
    # (MID, DILL, CIVIL) while accepting II, IV, VIII, XIII.
    ROMAN = re.compile(
        r"^(?=[MDCLXVI])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$"
    )
    # Tokens that keep their case regardless of how they appear in the filename.
    # Compared against the token with punctuation stripped, so "(nes)" matches.
    KEEP_UPPER = {
        "UFC", "TMNT", "AVGN", "NES", "SNES", "SNL", "MTV", "HBO", "PBS",
        "BBC", "CBS", "NBC", "ABC", "TV", "DVD", "VHS", "NFL", "NBA", "MLB",
        "NHL", "WWE", "WWF", "WCW", "USA", "UK", "FBI", "CIA", "NASA",
    }

    _DOT = "\x00"
    _DASH = "\x01"

    @staticmethod
    def _cap_part(part: str) -> str:
        core = re.sub(r"[^A-Za-z0-9]", "", part)
        if core and core.upper() in TitleParser.KEEP_UPPER:
            return part.upper()
        # Already-uppercase Roman numerals keep their case: "III" not "Iii"
        if len(part) > 1 and part.isupper() and TitleParser.ROMAN.match(part):
            return part
        return part.capitalize()

    @staticmethod
    def _cap(word: str) -> str:
        # capitalize() lowercases everything after the first char, which would
        # turn "C.O.P.S" into "C.o.p.s" and "He-Man" into "He-man".
        if "." in word:
            return word
        return "-".join(TitleParser._cap_part(p) for p in word.split("-"))

    @staticmethod
    def _clean(title: str) -> str:
        # Shield dots and inner hyphens from the separator cleanup, then restore
        title = TitleParser.ACRONYM.sub(
            lambda m: m.group(0).replace(".", TitleParser._DOT), title
        )
        title = TitleParser.ABBREV.sub(
            lambda m: m.group(0).replace(".", TitleParser._DOT), title
        )
        title = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", TitleParser._DASH, title)

        title = re.sub(r"[._-]", " ", title)  # separators to spaces
        title = re.sub(r"\s+", " ", title)  # collapse runs of whitespace
        title = title.strip()

        title = title.replace(TitleParser._DOT, ".").replace(TitleParser._DASH, "-")
        return " ".join(TitleParser._cap(w) for w in title.split())

    @staticmethod
    def parse_title(in_str: str, custom_patterns: list = None) -> str:
        if not in_str:
            return ""  # Consider defaulting to No Information or No Data to match TV Guides

        filename = in_str.strip()

        # Remove file extension
        filename = TitleParser.VIDEO_EXT.sub("", filename)

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
                return TitleParser._clean(match.group(group))

        # Fallback: return cleaned filename
        return TitleParser._clean(filename)