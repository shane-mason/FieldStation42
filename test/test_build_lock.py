"""
Tests for the per-station schedule build lock and the places that take it.

Running
-------
    env/bin/pytest test/test_build_lock.py -v
"""

import datetime
import multiprocessing
import os
import shutil
import signal
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fs42 import build_lock
from fs42.build_lock import BuildLockTimeout, station_build_lock

STATION = "Testy"
MIDNIGHT = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
BLOCK = datetime.timedelta(minutes=30)

HAS_FORK = "fork" in multiprocessing.get_all_start_methods()


class TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.server_conf = {"db_path": os.path.join(self.tmp, "test.db"), "normalize_titles": False}
        for target in ("fs42.build_lock.StationManager", "fs42.liquid_io.StationManager", "fs42.catalog_io.StationManager"):
            patcher = patch(target)
            sm = patcher.start()
            sm.return_value.server_conf = self.server_conf
            self.addCleanup(patcher.stop)

    def hold_in_thread(self, name=STATION):
        """Hold the lock in another thread until the returned release() is called."""
        acquired, release = threading.Event(), threading.Event()

        def holder():
            with station_build_lock(name):
                acquired.set()
                release.wait(5)

        t = threading.Thread(target=holder)
        t.start()
        self.assertTrue(acquired.wait(5))

        def done():
            release.set()
            t.join(5)

        self.addCleanup(done)
        return done


class LockTests(TempDbTestCase):
    def test_uncontended_lock_does_not_wait(self):
        with station_build_lock(STATION) as waited:
            self.assertFalse(waited)

    def test_lock_file_sits_next_to_the_database(self):
        with station_build_lock("Channel 5/HD"):
            pass
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "locks", "Channel_5_HD.lock")))

    def test_second_thread_waits_for_the_first(self):
        release = self.hold_in_thread()
        threading.Timer(0.3, release).start()
        started = time.monotonic()
        with station_build_lock(STATION) as waited:
            self.assertTrue(waited)
            self.assertGreaterEqual(time.monotonic() - started, 0.25)

    def test_timeout(self):
        self.hold_in_thread()
        with self.assertRaises(BuildLockTimeout):
            with station_build_lock(STATION, timeout=0.3):
                pass

    def test_other_stations_are_not_blocked(self):
        self.hold_in_thread("Other")
        with station_build_lock(STATION, timeout=0.3) as waited:
            self.assertFalse(waited)

    def test_reentrant_in_one_thread_but_still_excludes_other_threads(self):
        with station_build_lock(STATION):
            with station_build_lock(STATION, timeout=0.3) as waited:
                self.assertFalse(waited)
            result = []

            def other():
                try:
                    with station_build_lock(STATION, timeout=0.3):
                        result.append("got it")
                except BuildLockTimeout:
                    result.append("timed out")

            t = threading.Thread(target=other)
            t.start()
            t.join(5)
            self.assertEqual(["timed out"], result)
        # and the outer exit really released it
        with station_build_lock(STATION, timeout=0.3) as waited:
            self.assertFalse(waited)


def _hold_in_child(acquired, release):
    with station_build_lock(STATION):
        acquired.set()
        release.wait(10)


def _hold_in_child_until_killed(acquired):
    with station_build_lock(STATION):
        acquired.set()
        time.sleep(10)


@unittest.skipUnless(HAS_FORK, "needs fork so the child inherits the patched config")
class ProcessLockTests(TempDbTestCase):
    def start_holder(self):
        ctx = multiprocessing.get_context("fork")
        acquired, release = ctx.Event(), ctx.Event()
        proc = ctx.Process(target=_hold_in_child, args=(acquired, release))
        proc.start()
        self.addCleanup(proc.join, 5)
        self.addCleanup(release.set)
        self.assertTrue(acquired.wait(5))
        return proc, release

    def test_other_process_is_excluded_until_release(self):
        proc, release = self.start_holder()
        with self.assertRaises(BuildLockTimeout):
            with station_build_lock(STATION, timeout=0.3):
                pass
        release.set()
        proc.join(5)
        with station_build_lock(STATION, timeout=1):
            pass

    def test_killed_holder_leaves_no_stale_lock(self):
        # the child sleeps rather than waiting on an Event - killing an Event waiter wedges Event.set()
        ctx = multiprocessing.get_context("fork")
        acquired = ctx.Event()
        proc = ctx.Process(target=_hold_in_child_until_killed, args=(acquired,))
        proc.start()
        self.assertTrue(acquired.wait(5))
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(5)
        with station_build_lock(STATION, timeout=1):
            pass


def _blocks_between(start, end):
    blocks = []
    from fs42.liquid_blocks import LiquidBlock

    when = start
    while when < end:
        content = SimpleNamespace(dbid=1, title="Show")
        block = LiquidBlock(content, when, when + BLOCK, title="Show")
        block.plan = []
        blocks.append(block)
        when += BLOCK
    return blocks


class BuildCollisionTests(TempDbTestCase):
    """Real _increment / _delete_schedule and DB, with the slow planning replaced by a sleep."""

    def setUp(self):
        super().setUp()
        from fs42.liquid_io import LiquidIO

        self.io = LiquidIO()
        self.conf = {"network_name": STATION, "network_type": "standard", "schedule_offset": 0}

    def slow_schedule(self, in_build=None):
        from fs42.liquid_schedule import LiquidSchedule

        schedule = LiquidSchedule.__new__(LiquidSchedule)
        schedule.conf = self.conf

        def fluid(start, end):
            if in_build:
                in_build.set()
            time.sleep(0.3)
            self.io.put_liquid_blocks(STATION, _blocks_between(start, end))

        schedule._fluid = fluid
        return schedule

    def rows(self):
        with self.io._get_connection() as conn:
            return [
                (datetime.datetime.fromisoformat(s), datetime.datetime.fromisoformat(e))
                for s, e in conn.execute(
                    "SELECT start_time, end_time FROM liquid_blocks WHERE station=? ORDER BY start_time", (STATION,)
                )
            ]

    def test_two_concurrent_adds_do_not_overlap(self):
        threads = [threading.Thread(target=self.slow_schedule()._increment, args=("day",)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        rows = self.rows()
        self.assertEqual(96, len(rows))
        for (_, prev_end), (start, _) in zip(rows, rows[1:]):
            self.assertGreaterEqual(start, prev_end)
        self.assertEqual((MIDNIGHT, MIDNIGHT + datetime.timedelta(days=2)), self.io.get_liquid_extents(STATION))

    def test_reset_waits_for_a_running_add(self):
        from fs42.liquid_manager import LiquidManager

        self.io.put_liquid_blocks(STATION, _blocks_between(MIDNIGHT, MIDNIGHT + datetime.timedelta(days=1)))
        in_build = threading.Event()
        add = threading.Thread(target=self.slow_schedule(in_build)._increment, args=("day",))
        add.start()
        self.assertTrue(in_build.wait(5))

        manager = LiquidManager.__new__(LiquidManager)
        manager.reset_sequences = lambda conf: None
        manager._delete_schedule(self.conf)
        add.join(5)

        # without the lock the add would land after the delete and leave a schedule starting tomorrow
        self.assertEqual([], self.rows())


class AgentLockTests(TempDbTestCase):
    def setUp(self):
        super().setUp()
        from fs42.live_schedule_agent import ScheduleAgentWorker

        self.worker = ScheduleAgentWorker({"amount_to_add": "week", "trigger_add_at": "day"})
        self.station = {"network_name": STATION}
        self.schedule_cls = MagicMock()
        patcher = patch("fs42.liquid_schedule.LiquidSchedule", self.schedule_cls)
        patcher.start()
        self.addCleanup(patcher.stop)

    def extents(self, *ends):
        return patch("fs42.liquid_api.LiquidAPI.get_extents", side_effect=[(MIDNIGHT, e) for e in ends])

    def test_requested_build_skips_when_another_build_already_covered_now(self):
        with self.extents(datetime.datetime.now() + datetime.timedelta(days=1)):
            self.worker.build_until_now(self.station)
        self.schedule_cls.assert_not_called()

    def test_requested_build_adds_days_until_past_now(self):
        now = datetime.datetime.now()
        with self.extents(None, now, now + datetime.timedelta(days=1)):
            self.worker.build_until_now(self.station)
        self.assertEqual(2, self.schedule_cls.return_value.add_days.call_count)

    def test_topup_skips_when_another_build_already_topped_up(self):
        with self.extents(datetime.datetime.now() + datetime.timedelta(days=3)):
            self.worker.build_amount(self.station, "week")
        self.schedule_cls.assert_not_called()

    def test_topup_builds_when_still_needed(self):
        with self.extents(datetime.datetime.now() + datetime.timedelta(hours=2)):
            self.worker.build_amount(self.station, "week")
        self.schedule_cls.return_value.add_amount.assert_called_once_with("week")

    def test_agent_gives_up_on_a_lock_held_too_long(self):
        self.hold_in_thread()
        with patch("fs42.live_schedule_agent.BUILD_LOCK_TIMEOUT", 0.3), self.extents(None):
            with self.assertRaises(BuildLockTimeout):
                self.worker.build_until_now(self.station)
        self.schedule_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
