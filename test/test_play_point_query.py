"""
Tests for PlayPointQuery - the player's direct-from-database play point lookup.

The reference for "correct" is LiquidManager's in-memory algorithm, run over
the same blocks loaded the old way.

Running
-------
    env/bin/pytest test/test_play_point_query.py -v
"""

import datetime
import os
import random
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fs42.block_plan import BlockPlanEntry
from fs42.liquid_blocks import LiquidBlock

STATION = "Testy"
BRB = "/media/brb.mp4"
DAY_START = datetime.datetime(2026, 11, 13, 0, 0, 0)
BLOCK = datetime.timedelta(minutes=30)
GAP_START = DAY_START + 10 * BLOCK
SHORT_PLAN_BLOCK = 4

STATIONS = {
    STATION: {"network_name": STATION, "network_type": "standard", "be_right_back_media": BRB},
    "Streamy": {
        "network_name": "Streamy",
        "network_type": "streaming",
        "streams": [{"url": "http://example/stream", "duration": 600}],
    },
}


def make_blocks():
    blocks = []
    for i in range(48):
        start = DAY_START + i * BLOCK
        if start == GAP_START:
            # leave one block-sized hole in the schedule
            continue
        content = SimpleNamespace(dbid=1000 + i, title=f"Show {i}")
        block = LiquidBlock(content, start, start + BLOCK, title=f"Show {i}")
        if i == SHORT_PLAN_BLOCK:
            # plan ends ten minutes before the block does
            block.plan = [BlockPlanEntry(f"/media/{i}/a.mp4", 0, 600), BlockPlanEntry(f"/media/{i}/b.mp4", 0, 600)]
        else:
            block.plan = [
                BlockPlanEntry(f"/media/{i}/a.mp4", 5, 1320),
                BlockPlanEntry(f"/media/{i}/commercial.mp4", 0, 180, content_type="commercial"),
                BlockPlanEntry(f"/media/{i}/b.mp4", 0, 300),
            ]
        blocks.append(block)
    return blocks


class PlayPointQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        server_conf = {"db_path": os.path.join(self.tmp, "test.db"), "normalize_titles": False}

        for target in (
            "fs42.liquid_io.StationManager",
            "fs42.catalog_io.StationManager",
            "fs42.play_point_query.StationManager",
            "fs42.liquid_manager.StationManager",
        ):
            patcher = patch(target)
            sm = patcher.start()
            sm.return_value.server_conf = server_conf
            sm.return_value.station_by_name.side_effect = STATIONS.get
            self.addCleanup(patcher.stop)

        from fs42.liquid_io import LiquidIO
        from fs42.liquid_manager import LiquidManager
        from fs42.play_point_query import PlayPointQuery

        self.io = LiquidIO()
        self.io.put_liquid_blocks(STATION, make_blocks())
        self.query = PlayPointQuery()

        # an un-shared LiquidManager over the same blocks, without touching the borg state
        self.reference = LiquidManager.__new__(LiquidManager)
        self.reference.schedules = {STATION: self.io.get_liquid_blocks(STATION)}

    def assertSamePlayPoint(self, expected, actual, when):
        self.assertIsNotNone(actual, when)
        self.assertEqual(expected.index, actual.index, when)
        self.assertEqual(expected.offset, actual.offset, when)
        self.assertEqual(expected.block_title, actual.block_title, when)
        self.assertEqual(
            [(p.path, p.skip, p.duration, p.content_type) for p in expected.plan],
            [(p.path, p.skip, p.duration, p.content_type) for p in actual.plan],
            when,
        )

    def test_matches_liquid_manager_at_random_times(self):
        rng = random.Random(42)
        span = 48 * BLOCK.total_seconds()
        checked = 0
        while checked < 500:
            when = DAY_START + datetime.timedelta(seconds=rng.uniform(0, span))
            if GAP_START <= when <= GAP_START + BLOCK:
                continue
            self.assertSamePlayPoint(
                self.reference.get_play_point(STATION, when), self.query.get_play_point(STATION, when), when
            )
            checked += 1

    def test_matches_liquid_manager_mid_entry_and_on_entry_edges(self):
        start = DAY_START + 2 * BLOCK
        for seconds in (0.5, 1319.9, 1320, 1320.001, 1499.999, 1500, 1799.5):
            when = start + datetime.timedelta(seconds=seconds)
            self.assertSamePlayPoint(
                self.reference.get_play_point(STATION, when), self.query.get_play_point(STATION, when), when
            )

    def test_exact_block_boundary_returns_the_starting_block(self):
        when = DAY_START + 3 * BLOCK
        play_point = self.query.get_play_point(STATION, when)
        self.assertEqual("Show 3", play_point.block_title)
        self.assertEqual(0, play_point.index)
        self.assertEqual(0, play_point.offset)

    def test_short_plan_falls_back_to_be_right_back_media(self):
        when = DAY_START + SHORT_PLAN_BLOCK * BLOCK + datetime.timedelta(minutes=25)
        play_point = self.query.get_play_point(STATION, when)
        self.assertSamePlayPoint(self.reference.get_play_point(STATION, when), play_point, when)
        self.assertEqual(BRB, play_point.plan[0].path)
        self.assertEqual(300, play_point.plan[0].duration)

    def test_first_and_last_moment_of_schedule(self):
        start, end = DAY_START, DAY_START + 48 * BLOCK
        self.assertEqual("Show 0", self.query.get_play_point(STATION, start).block_title)
        self.assertEqual("Show 47", self.query.get_programming_block(STATION, end).title)

    def test_hole_in_schedule_returns_none(self):
        when = GAP_START + datetime.timedelta(minutes=10)
        self.assertIsNone(self.query.get_programming_block(STATION, when))
        self.assertIsNone(self.query.get_play_point(STATION, when))

    def test_before_start(self):
        from fs42.liquid_manager import ScheduleQueryNotInBounds
        from fs42.play_point_query import ScheduleBeforeStart

        with self.assertRaises(ScheduleBeforeStart) as ctx:
            self.query.get_play_point(STATION, DAY_START - datetime.timedelta(seconds=1))
        self.assertIsInstance(ctx.exception, ScheduleQueryNotInBounds)

    def test_past_end(self):
        from fs42.liquid_manager import ScheduleQueryNotInBounds
        from fs42.play_point_query import SchedulePastEnd

        with self.assertRaises(SchedulePastEnd) as ctx:
            self.query.get_play_point(STATION, DAY_START + 48 * BLOCK + datetime.timedelta(seconds=1))
        self.assertIsInstance(ctx.exception, ScheduleQueryNotInBounds)

    def test_no_schedule(self):
        from fs42.liquid_manager import ScheduleNotFound

        STATIONS["Empty"] = {"network_name": "Empty", "network_type": "standard"}
        self.addCleanup(STATIONS.pop, "Empty")
        with self.assertRaises(ScheduleNotFound):
            self.query.get_play_point("Empty", DAY_START)

    def test_streaming_station(self):
        play_point = self.query.get_play_point("Streamy", DAY_START)
        self.assertEqual(1, len(play_point.plan))
        self.assertTrue(play_point.plan[0].is_stream)
        self.assertEqual("http://example/stream", play_point.plan[0].path)

    def test_extents(self):
        self.assertEqual((DAY_START, DAY_START + 48 * BLOCK), self.query.get_extents(STATION))
        self.assertEqual((None, None), self.query.get_extents("Nobody"))

    def test_prune_removes_only_blocks_that_ended_before_cutoff(self):
        cutoff = DAY_START + 20 * BLOCK + datetime.timedelta(minutes=10)
        removed = self.io.prune_liquid_blocks(cutoff)
        # blocks 0-19 ended at or before 20 * BLOCK, minus the one in the hole
        self.assertEqual(19, removed)
        self.assertEqual((DAY_START + 20 * BLOCK, DAY_START + 48 * BLOCK), self.query.get_extents(STATION))
        self.assertEqual("Show 20", self.query.get_play_point(STATION, cutoff).block_title)


if __name__ == "__main__":
    unittest.main()
