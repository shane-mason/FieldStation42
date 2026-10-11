import datetime
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.catalog import ShowCatalog  # noqa: E402
from fs42.catalog_entry import MatchingContentNotFound  # noqa: E402
from fs42.liquid_blocks import LiquidBlock  # noqa: E402

MONDAY_8PM = datetime.datetime(2026, 10, 12, 20, 0)


def _catalog(station_strategy):
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = {
        "network_name": "T", "break_strategy": station_strategy, "break_duration": 120,
        "commercial_free": False, "bump_dir": "bump", "monday": {"20": {"tags": "drama"}},
    }
    catalog.clip_index = {
        "bump": [SimpleNamespace(path="bump.mp4", duration=5, hints=[], tag="bump", count=0, content_type="bump", media_type="video")],
        "bump-prebump": [], "bump-postbump": [],
    }
    catalog._l = logging.getLogger("test")
    catalog.min_gap = 3

    def find_commercial(seconds, when, commercial_dir=None):
        if seconds < 30:
            raise MatchingContentNotFound("nothing fits")
        return SimpleNamespace(path="ad.mp4", duration=30, content_type="commercial", media_type="video")

    catalog.find_commercial = find_commercial
    return catalog


def _show_segments(station_strategy, block_strategy):
    show = SimpleNamespace(path="drama.mp4", realpath="drama.mp4", duration=1320, title="Drama", content_type="feature", media_type="video")
    break_info = {"start_bump": None, "end_bump": None, "bump_dir": None, "commercial_dir": None}
    block = LiquidBlock(show, MONDAY_8PM, MONDAY_8PM + datetime.timedelta(minutes=30), "Drama", block_strategy, break_info)
    no_markers = MagicMock()
    no_markers.return_value.get_chapters.return_value = []
    no_markers.return_value.get_breaks.return_value = []
    with patch("fs42.liquid_blocks.FluidBuilder", no_markers):
        block.make_plan(_catalog(station_strategy))
    segments, in_show = 0, False
    for entry in block.plan:
        if entry.path == "drama.mp4" and not in_show:
            segments += 1
        in_show = entry.path == "drama.mp4"
    return segments, block.plan


def test_reel_fill_uses_strategy_passed_in():
    assert len(_catalog("end").make_reel_fill(MONDAY_8PM, 480, break_strategy="standard")) > 2
    assert len([b for b in _catalog("standard").make_reel_fill(MONDAY_8PM, 480, break_strategy="end") if b.duration]) == 1


def test_standard_override_on_end_station_spreads_breaks_through_show():
    segments, _ = _show_segments(station_strategy="end", block_strategy="standard")
    assert segments > 2


def test_end_override_on_standard_station_plays_one_break_after_show():
    segments, plan = _show_segments(station_strategy="standard", block_strategy="end")
    assert segments == 1 and plan[0].path == "drama.mp4"
    assert sum(1 for e in plan if e.path == "bump.mp4") == 2
