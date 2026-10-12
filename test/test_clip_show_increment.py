import datetime
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.catalog import ShowCatalog  # noqa: E402
from fs42.liquid_schedule import LiquidSchedule  # noqa: E402

START = datetime.datetime(2026, 10, 12, 20, 0)


def _clip(duration):
    return SimpleNamespace(path="/content/synth/clip.mp4", realpath="/content/synth/clip.mp4", duration=duration,
                           title="Clip", content_type="feature", media_type="video", hints=[], tag="synth", count=0)


def _schedule(increment):
    conf = {
        "network_name": "SynthWave", "content_dir": "/content", "commercial_free": True,
        "schedule_increment": increment, "break_strategy": "standard", "break_duration": 120, "bump_dir": "bump",
        "clip_shows": {"synth": {"tags": "synth", "duration": 3600, "total_duration": 3600}},
    }
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = conf
    catalog.clip_index = {}
    catalog._l = logging.getLogger("test")
    catalog.min_gap = 3
    catalog.gather_clip_content = MagicMock(return_value=[_clip(1400), _clip(1400)])
    sched = LiquidSchedule.__new__(LiquidSchedule)
    sched.conf = conf
    sched.catalog = catalog
    return sched


def test_zero_increment_ends_at_content_and_needs_no_bumps():
    sched = _schedule(0)
    block, next_mark = sched._clip_fill("synth", START, {"tags": "synth"})
    assert next_mark == START + datetime.timedelta(seconds=2800)
    block.make_plan(sched.catalog)
    assert not block.reel_blocks


def test_nonzero_increment_uses_total_duration():
    sched = _schedule(30)
    _, next_mark = sched._clip_fill("synth", START, {"tags": "synth"})
    assert next_mark == START + datetime.timedelta(hours=1)
