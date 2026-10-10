"""
Tests for LiquidSchedule._calc_target_duration, which sizes a schedule slot
from the content plus any start/end bumps, rounded up to the schedule increment.

Running
-------
    python3 -m unittest test.test_target_duration -v
"""

import sys
import unittest
from unittest.mock import MagicMock

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

from fs42.liquid_schedule import LiquidSchedule  # noqa: E402

MOVIE = 5390.518467  # Catwoman (2004) - just under 90 minutes
BUMP = 10


def _sched(increment=30):
    sched = LiquidSchedule.__new__(LiquidSchedule)
    sched.conf = {"schedule_increment": increment}
    return sched


def _info(start=None, end=None):
    return {
        "start_bump": {"duration": start} if start else None,
        "end_bump": {"duration": end} if end else None,
    }


class TestCalcTargetDuration(unittest.TestCase):
    def test_no_bumps_unchanged(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE), 5400)
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, _info()), 5400)

    def test_no_break_info_unchanged(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, None), 5400)

    def test_both_bumps_push_to_next_increment(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, _info(BUMP, BUMP)), 7200)

    def test_start_bump_only(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, _info(start=BUMP)), 7200)

    def test_end_bump_only(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, _info(end=BUMP)), 7200)

    def test_bumps_that_still_fit_do_not_grow_slot(self):
        self.assertEqual(_sched()._calc_target_duration(1500, 30, _info(BUMP, BUMP)), 1800)

    def test_zero_increment_is_exact(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 0), MOVIE)
        self.assertAlmostEqual(
            _sched()._calc_target_duration(MOVIE, 0, _info(BUMP, BUMP)), MOVIE + 2 * BUMP
        )

    def test_default_increment_from_conf(self):
        self.assertEqual(_sched(60)._calc_target_duration(MOVIE, None, _info(BUMP, BUMP)), 7200)


MIN = 60


def _std(sched, minutes, info=None, strategy="standard", increment=30):
    return sched._calc_target_duration(minutes * MIN, increment, info, strategy) / MIN


class TestCommercialRoom(unittest.TestCase):
    def test_tight_short_content_stays(self):
        # bumping would leave over the maximum share of commercials
        self.assertEqual(_std(_sched(), 29), 30)
        self.assertEqual(_std(_sched(), 58), 60)

    def test_enough_room_unchanged(self):
        self.assertEqual(_std(_sched(), 28), 30)
        self.assertEqual(_std(_sched(), 126), 150)

    def test_movie_bumps_up(self):
        self.assertEqual(_std(_sched(), 86), 120)
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, None, "standard"), 7200)

    def test_bumps_count_as_non_content(self):
        self.assertEqual(_sched()._calc_target_duration(MOVIE, 30, _info(BUMP, BUMP), "standard"), 7200)

    def test_commercial_free_never_bumps(self):
        sched = _sched()
        sched.conf["commercial_free"] = True
        self.assertEqual(_std(sched, 86), 90)

    def test_zero_increment_never_bumps(self):
        self.assertEqual(_std(_sched(0), 86, increment=0), 86)

    def test_end_strategy_never_bumps(self):
        self.assertEqual(_std(_sched(), 86, strategy="end"), 90)

    def test_no_strategy_never_bumps(self):
        self.assertEqual(_std(_sched(), 86, strategy=None), 90)


if __name__ == "__main__":
    unittest.main()
