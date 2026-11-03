"""
Reader for ``.strm`` stub files: tiny text files that stand in for a video the
player streams from a URL (an Internet Archive download link, for example)
instead of reading it from disk.

A stub looks like this::

    https://archive.org/download/some-item/episode-01.mp4
    #duration=1425
    #start=12.5
    #crop=640:480:40:0
    #aid=2

Only the first line (the URL or a local file path) is required, but the catalog
scan needs ``#duration`` because it cannot probe a remote file without
downloading it.
"""

STUB_EXTENSION = ".strm"


def is_stub(path):
    return str(path).lower().endswith(STUB_EXTENSION)


def read_stub(path):
    """Parse a stub file.

    Returns a dict:
        target    URL or local path to play (None if the stub has no such line)
        start     seconds to skip at the start of the target (default 0.0)
        duration  length in seconds, after the ``#start`` trim (None if not given)
        crop      mpv ``video-crop`` value ("WxH+X+Y") or "" for none
        aid       audio track id as a string, or "auto"

    Unknown lines and malformed values are ignored.
    """
    stub = {"target": None, "start": 0.0, "duration": None, "crop": "", "aid": "auto"}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                key, _, value = line[1:].partition("=")
                _apply_option(stub, key.strip().lower(), value.strip())
            elif stub["target"] is None:
                stub["target"] = line
    return stub


def _apply_option(stub, key, value):
    if key in ("start", "duration"):
        try:
            number = float(value)
        except ValueError:
            return
        if number >= 0:
            stub[key] = number
    elif key == "crop":
        stub["crop"] = crop_to_mpv(value)
    elif key == "aid" and value.isdigit():
        stub["aid"] = value


def crop_to_mpv(value):
    """Convert ffmpeg-style ``w:h:x:y`` (what ``cropdetect`` prints) to mpv's ``WxH+X+Y``.

    Returns "" when the value is not four non-negative integers.
    """
    parts = value.split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return ""
    w, h, x, y = parts
    return f"{w}x{h}+{x}+{y}"
