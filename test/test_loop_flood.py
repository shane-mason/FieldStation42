import datetime
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.liquid_schedule import LiquidSchedule  # noqa: E402

MIN = 60
MIDNIGHT = datetime.datetime(2026, 3, 1)
DAY = datetime.timedelta(days=1)


def _clip(name, minutes):
    return SimpleNamespace(path=f"/loop/{name}.mp4", duration=minutes * MIN, content_type="feature", media_type="video")


def _content():
    return [_clip(f"c{i}", m) for i, m in enumerate([50, 70, 45, 95, 30, 62, 41])]


def _flood(content, start, end, **conf):
    sched = LiquidSchedule.__new__(LiquidSchedule)
    sched.conf = {"network_name": "Loop", **conf}
    sched.catalog = MagicMock()
    sched.catalog.get_all_by_tag.return_value = content
    sched._l = logging.getLogger("test")
    with patch("fs42.liquid_schedule.LiquidAPI") as api:
        sched._flood(start, end)
    return api.add_blocks.call_args[0][1]


def _paths(blocks):
    return [entry.path for block in blocks for entry in block.plan]


def test_plays_through_day_marks():
    content = _content()
    blocks = _flood(content, MIDNIGHT, MIDNIGHT + 3 * DAY)
    paths = _paths(blocks)
    n = len(content)

    assert len(blocks) == 3
    assert all(paths[i] == paths[i % n] for i in range(len(paths)))
    for block in blocks:
        assert all(entry.skip == 0 for entry in block.plan)
        planned = sum(entry.duration for entry in block.plan)
        assert block.start_time + datetime.timedelta(seconds=planned) == block.end_time


def test_blocks_are_contiguous_and_stay_near_midnight():
    blocks = _flood(_content(), MIDNIGHT, MIDNIGHT + 7 * DAY)
    longest = datetime.timedelta(minutes=95)

    assert len(blocks) == 7
    assert blocks[0].start_time == MIDNIGHT
    for day, block in enumerate(blocks, start=1):
        mark = MIDNIGHT + day * DAY
        assert mark <= block.end_time < mark + longest
    for prev, block in zip(blocks, blocks[1:]):
        assert block.start_time == prev.end_time


def test_continuing_build_aims_for_next_midnight():
    start = MIDNIGHT + datetime.timedelta(minutes=40)
    blocks = _flood(_content(), start, start + DAY)

    assert len(blocks) == 1
    assert blocks[0].start_time == start
    assert MIDNIGHT + DAY <= blocks[0].end_time < MIDNIGHT + DAY + datetime.timedelta(minutes=95)


def test_marks_follow_schedule_offset():
    start = MIDNIGHT + datetime.timedelta(minutes=5)
    blocks = _flood(_content(), start, start + 2 * DAY, schedule_offset=5)

    assert len(blocks) == 2
    for day, block in enumerate(blocks, start=1):
        assert start + day * DAY <= block.end_time


def test_clip_longer_than_a_day_is_played_whole():
    blocks = _flood([_clip("epic", 30 * 60)], MIDNIGHT, MIDNIGHT + 3 * DAY)

    assert [b.end_time - b.start_time for b in blocks] == [datetime.timedelta(hours=30)] * 3
    assert blocks[-1].end_time >= MIDNIGHT + 3 * DAY


@pytest.mark.parametrize("shuffle", [False, True])
def test_each_pass_plays_every_clip_once(shuffle):
    content = _content()
    paths = _paths(_flood(content, MIDNIGHT, MIDNIGHT + 3 * DAY, shuffle_loop=shuffle))
    n = len(content)
    every = sorted(c.path for c in content)

    for i in range(0, len(paths) - n + 1, n):
        assert sorted(paths[i:i + n]) == every


def test_unshuffled_loop_plays_in_catalog_order():
    content = _content()
    paths = _paths(_flood(content, MIDNIGHT, MIDNIGHT + 2 * DAY, shuffle_loop=False))

    assert paths == [content[i % len(content)].path for i in range(len(paths))]


def test_catalog_list_is_not_reordered():
    content = _content()
    original = list(content)
    _flood(content, MIDNIGHT, MIDNIGHT + 2 * DAY, shuffle_loop=True)

    assert content == original


def test_no_content_raises():
    with pytest.raises(ValueError):
        _flood(None, MIDNIGHT, MIDNIGHT + DAY)
