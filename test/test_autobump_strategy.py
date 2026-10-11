import datetime
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.catalog import ShowCatalog  # noqa: E402

WHEN = datetime.datetime(2026, 10, 12, 20, 0)


def _bump(name):
    return SimpleNamespace(path=f"bump/{name}.mp4", duration=5, hints=[], tag="bump", count=0)


def _catalog(strategy, with_pre=True, with_post=True):
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = {
        "network_name": "Toons",
        "bump_dir": "bump",
        "commercial_free": False,
        "autobump": {"title": "Toons TV", "strategy": strategy},
    }
    catalog.clip_index = {
        "bump": [_bump("regular")],
        "bump-prebump": [_bump("pre")] if with_pre else [],
        "bump-postbump": [_bump("post")] if with_post else [],
    }
    catalog._l = logging.getLogger("test")
    catalog.find_commercial = lambda seconds, when, commercial_dir=None: SimpleNamespace(path="ad.mp4", duration=seconds)
    return catalog


def _ends(block):
    return block.start_bump.path, block.end_bump.path


def test_start_strategy_closes_with_post_bump():
    start, end = _ends(_catalog("start").make_reel_block(WHEN, target_duration=120))
    assert start.startswith(":autobump:=")
    assert end == "bump/post.mp4"


def test_start_strategy_falls_back_to_regular_bump_without_post():
    _, end = _ends(_catalog("start", with_post=False).make_reel_block(WHEN, target_duration=120))
    assert end == "bump/regular.mp4"


def test_end_strategy_opens_with_pre_bump():
    start, end = _ends(_catalog("end").make_reel_block(WHEN, target_duration=120))
    assert start == "bump/pre.mp4"
    assert end.startswith(":autobump:=")


def test_both_strategy_generates_both():
    start, end = _ends(_catalog("both").make_reel_block(WHEN, target_duration=120))
    assert start.startswith(":autobump:=") and end.startswith(":autobump:=")
