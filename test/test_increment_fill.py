"""
Tests for filling a schedule increment with short content: quarter-increment
sizing in _calc_target_duration, the fill loop in _fluid, and
SequenceAPI.peek_next_in_sequence.

Running
-------
    python3 -m unittest test.test_increment_fill -v
"""

import datetime
import logging
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.catalog import MatchingContentNotFound  # noqa: E402
from fs42.liquid_blocks import LiquidBlock  # noqa: E402
from fs42.liquid_schedule import LiquidSchedule  # noqa: E402
from fs42.sequence import NamedSequence  # noqa: E402
from fs42.sequence_api import SequenceAPI  # noqa: E402

MIN = 60
CONTENT_DIR = "/content"
START = datetime.datetime(2026, 1, 5, 20, 0)


def _minutes(td):
    return td.total_seconds() / MIN


class TestQuarterIncrementSizing(unittest.TestCase):
    def _target(self, seconds, increment):
        sched = LiquidSchedule.__new__(LiquidSchedule)
        sched.conf = {"schedule_increment": increment}
        return sched._calc_target_duration(seconds, increment)

    def test_short_content_uses_quarter_steps(self):
        self.assertEqual(self._target(11 * MIN, 30), 15 * MIN)
        self.assertEqual(self._target(20 * MIN, 60), 30 * MIN)

    def test_content_over_half_uses_full_increment(self):
        self.assertEqual(self._target(22 * MIN, 30), 30 * MIN)

    def test_step_never_exceeds_small_increment(self):
        self.assertEqual(self._target(20, 1), 60)
        self.assertEqual(self._target(1 * MIN, 3), 3 * MIN)


def _entry(name, minutes, count=0, tag="cartoons"):
    path = f"{CONTENT_DIR}/{tag}/{name}.mp4"
    return SimpleNamespace(
        path=path, realpath=path, title=name, duration=minutes * MIN, tag=tag, count=count
    )


class FakeCatalog:
    def __init__(self, entries):
        self.entries = entries
        self.by_path = {e.path: e for e in entries}

    def find_candidate(self, tag, seconds, when, exclusion_index=None, proposed_start=None,
                       meta_hints=None, min_duration=None, max_duration=None, candidate_filter=None):
        matches = [
            e for e in self.entries
            if (min_duration is None or e.duration >= min_duration)
            and (max_duration is None or e.duration <= max_duration)
            and (candidate_filter is None or candidate_filter(e))
        ]
        if not matches:
            raise MatchingContentNotFound(f"nothing for {tag}")
        result = min(matches, key=lambda e: e.count)
        result.count += 1
        return result

    def entry_by_fpath(self, fpath):
        return self.by_path.get(fpath)


def _build(entries, slot, hours=1, increment=30):
    sched = LiquidSchedule.__new__(LiquidSchedule)
    sched.conf = {
        "network_name": "stn",
        "break_strategy": "standard",
        "schedule_increment": increment,
        "clip_shows": {},
        "content_dir": CONTENT_DIR,
    }
    sched._l = logging.getLogger("test-increment-fill")
    sched.catalog = FakeCatalog(entries)

    with patch.object(LiquidSchedule, "_build_exclusion_index", return_value={}), \
         patch("fs42.liquid_schedule.SlotReader.get_slot", return_value=(slot, 20)), \
         patch("fs42.liquid_schedule.LiquidAPI") as api, \
         patch("fs42.liquid_schedule.CatalogAPI"), \
         patch.object(LiquidBlock, "make_plan"):
        sched._fluid(START, START + datetime.timedelta(hours=hours))
    return api.add_blocks.call_args[0][1]


class TestTagSlotFill(unittest.TestCase):
    def test_two_short_items_share_an_increment(self):
        blocks = _build([_entry("A", 11), _entry("C", 10.5), _entry("B", 5)], {"tags": "cartoons"}, hours=0.5)
        self.assertEqual([b.title for b in blocks], ["A", "C"])
        self.assertEqual(_minutes(blocks[0].end_time - START), 15)
        self.assertEqual(blocks[1].start_time, blocks[0].end_time)
        self.assertEqual(_minutes(blocks[1].end_time - START), 30)

    def test_extra_item_must_be_at_least_90_percent_of_first(self):
        # B wins on order without a floor; at 5 of 11 minutes it is too short
        blocks = _build([_entry("B", 5, count=1), _entry("A", 11)], {"tags": "cartoons"}, hours=0.5)
        self.assertEqual([b.title for b in blocks], ["A", "A"])

    def test_unused_time_is_padded_to_the_increment(self):
        # 14 minutes sizes to 20; nothing at least 90% as long fits the last 10
        blocks = _build([_entry("A", 14)], {"tags": "cartoons"}, hours=0.5)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(_minutes(blocks[0].end_time - START), 30)


class _SequenceDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = patch("fs42.sequence_io.StationManager")
        station_manager = patcher.start()
        station_manager.return_value.server_conf = {"db_path": os.path.join(self.tmp, "test.db")}
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

        from fs42.sequence_io import SequenceIO
        self.sio = SequenceIO()

    def _put(self, tag_path, entries, parent_tag=None):
        ns = NamedSequence("stn", "seq", tag_path, 0.0, 1.0, 0, [e.path for e in entries], initialized=True)
        if parent_tag:
            ns.parent_tag = parent_tag
        self.sio.put_sequence("stn", ns)


class TestPeekNextInSequence(_SequenceDB):
    STATION = {"network_name": "stn"}

    def test_peek_does_not_advance(self):
        eps = [_entry(f"ep{i}", 11) for i in range(2)]
        self._put("cartoons", eps)
        self.assertEqual(SequenceAPI.peek_next_in_sequence(self.STATION, "seq", "cartoons").fpath, eps[0].path)
        self.assertEqual(SequenceAPI.get_next_in_sequence(self.STATION, "seq", "cartoons").fpath, eps[0].path)

    def test_peek_is_none_at_end_of_plain_sequence(self):
        self._put("cartoons", [_entry("ep0", 11)])
        SequenceAPI.get_next_in_sequence(self.STATION, "seq", "cartoons")
        self.assertIsNone(SequenceAPI.peek_next_in_sequence(self.STATION, "seq", "cartoons"))

    def test_peek_is_none_at_end_of_child_sequence(self):
        self._put("shows/ShowA", [_entry("a0", 11, tag="shows/ShowA")], parent_tag="shows")
        self._put("shows/ShowB", [_entry("b0", 11, tag="shows/ShowB")], parent_tag="shows")
        SequenceAPI.get_next_in_sequence(self.STATION, "seq", "shows")
        self.assertIsNone(SequenceAPI.peek_next_in_sequence(self.STATION, "seq", "shows"))


class TestSequenceSlotFill(_SequenceDB):
    def test_shorter_episode_pairs_and_end_is_not_wrapped(self):
        eps = [_entry("ep0", 11), _entry("ep1", 9), _entry("ep2", 11)]
        self._put("cartoons", eps)
        blocks = _build(eps, {"tags": "cartoons", "sequence": "seq"})
        self.assertEqual([b.title for b in blocks], ["ep0", "ep1", "ep2"])
        self.assertEqual(_minutes(blocks[1].end_time - START), 30)
        self.assertEqual(_minutes(blocks[2].end_time - START), 60)

    def test_random_show_does_not_mix_shows_in_an_increment(self):
        a = [_entry(f"a{i}", 11, tag="shows/ShowA") for i in range(3)]
        b = [_entry(f"b{i}", 11, tag="shows/ShowB") for i in range(3)]
        self._put("shows/ShowA", a, parent_tag="shows")
        self._put("shows/ShowB", b, parent_tag="shows")
        slot = {"tags": "shows", "sequence": "seq", "sequence_strategy": "random_show"}
        blocks = _build(a + b, slot)

        self.assertEqual(len(blocks), 3)
        first_show = blocks[0].title[0]
        self.assertEqual([blk.title[0] for blk in blocks], [first_show] * 3)
        self.assertEqual(_minutes(blocks[2].end_time - START), 60)


if __name__ == "__main__":
    unittest.main()
