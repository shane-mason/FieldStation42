import datetime
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.liquid_blocks import LiquidWebBlock  # noqa: E402

TEN_PM = datetime.datetime(2026, 10, 12, 22, 0)


def _entry(path, duration):
    return SimpleNamespace(path=path, duration=duration, content_type="feature", media_type="video", title=path)


def _plan(start, end, sign_off=None, autobump_seconds=3600):
    block = LiquidWebBlock(_entry(":autobump:=http://x/bump.html", autobump_seconds), start, end, "Offair", sign_off=sign_off)
    block.make_plan(None)
    return [(e.path, e.duration) for e in block.plan]


def test_autobump_alone_fills_the_hour():
    assert _plan(TEN_PM, TEN_PM + datetime.timedelta(hours=1)) == [(":autobump:=http://x/bump.html", 3600)]


def test_sign_off_plays_before_the_autobump():
    plan = _plan(TEN_PM, TEN_PM + datetime.timedelta(hours=1), sign_off=_entry("runtime/signoff.mp4", 30), autobump_seconds=3570)
    assert plan == [("runtime/signoff.mp4", 30), (":autobump:=http://x/bump.html", 3570)]


def test_autobump_is_clipped_to_a_short_block():
    start = TEN_PM + datetime.timedelta(minutes=40)
    assert _plan(start, TEN_PM + datetime.timedelta(hours=1)) == [(":autobump:=http://x/bump.html", 1200)]


def test_sign_off_longer_than_block_is_clipped_and_autobump_dropped():
    start = TEN_PM + datetime.timedelta(minutes=59, seconds=40)
    plan = _plan(start, TEN_PM + datetime.timedelta(hours=1), sign_off=_entry("runtime/signoff.mp4", 30), autobump_seconds=1)
    assert plan == [("runtime/signoff.mp4", 20)]


def test_off_air_autobump_has_no_lookahead_tag():
    from fs42.liquid_schedule import LiquidSchedule
    block = LiquidWebBlock(_entry(":autobump:=http://x/bump.html", 3600), TEN_PM, TEN_PM + datetime.timedelta(hours=1), "Offair")
    block.content.tag = ":autobump:"
    assert LiquidSchedule._get_block_tag(block) is None
