"""
Tests for ScheduleAgentWorker's job ordering, dedup and cooldown rules.

Builds, pruning and station lookups are replaced with recorders, and the
clock is fake, so nothing touches a database.

Running
-------
    env/bin/pytest test/test_live_schedule_agent.py -v
"""

import unittest
from queue import Empty

from fs42.live_schedule_agent import (
    CHECK_INTERVAL,
    FIRST_PLAY_FALLBACK,
    REQUEST_COOLDOWN,
    ScheduleAgentWorker,
)

CONF = {"amount_to_add": "week", "trigger_add_at": "day"}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RecordingWorker(ScheduleAgentWorker):
    def __init__(self, conf=CONF, clock=None, needing_topup=("A", "B", "C")):
        self.clock = clock or FakeClock()
        super().__init__(conf, clock=self.clock)
        self.calls = []
        self.needing_topup = list(needing_topup)
        self.stations = {name: {"network_name": name, "_has_schedule": True} for name in "ABCDE"}
        self.stations["Web"] = {"network_name": "Web", "_has_schedule": False}
        self.fail_builds = False

    def lookup_station(self, network_name):
        return self.stations.get(network_name)

    def build_until_now(self, station):
        self.calls.append(("requested", station["network_name"]))
        if self.fail_builds:
            raise RuntimeError("boom")

    def build_amount(self, station, amount):
        self.calls.append(("topup", station["network_name"], amount))

    def stations_needing_topup(self):
        self.calls.append(("check",))
        return [self.stations[name] for name in self.needing_topup]

    def prune(self):
        self.calls.append(("prune",))

    def request(self, name):
        self.handle_message(("build", name, self.clock()))

    def run_until_idle(self, limit=50):
        for _ in range(limit):
            if not self.has_work():
                return
            self.step()
        raise AssertionError("worker never went idle")

    def builds(self):
        return [c for c in self.calls if c[0] in ("requested", "topup")]


class RequestTests(unittest.TestCase):
    def test_requested_build_prunes_then_builds(self):
        w = RecordingWorker()
        w.request("A")
        w.run_until_idle()
        self.assertEqual([("prune",), ("requested", "A")], w.calls)

    def test_duplicate_requests_while_queued_build_once(self):
        w = RecordingWorker()
        for _ in range(5):
            w.request("A")
        w.run_until_idle()
        self.assertEqual([("requested", "A")], w.builds())

    def test_requests_sent_while_the_build_ran_are_ignored(self):
        w = RecordingWorker()
        sent_during_build = w.clock()
        w.request("A")
        w.clock.advance(30)
        w.run_until_idle()
        w.handle_message(("build", "A", sent_during_build + 10))
        w.run_until_idle()
        self.assertEqual([("requested", "A")], w.builds())
        self.assertNotIn("A", w._warned)

    def test_request_inside_cooldown_is_ignored_and_warned_once(self):
        w = RecordingWorker()
        w.request("A")
        w.run_until_idle()
        w.clock.advance(5)
        with self.assertLogs("ScheduleAgent", level="ERROR") as logs:
            w.request("A")
            w.request("A")
        w.run_until_idle()
        self.assertEqual(1, len(logs.output))
        self.assertEqual([("requested", "A")], w.builds())

    def test_request_after_cooldown_builds_again(self):
        w = RecordingWorker()
        w.request("A")
        w.run_until_idle()
        w.clock.advance(REQUEST_COOLDOWN + 1)
        w.request("A")
        w.run_until_idle()
        requested = [c for c in w.builds() if c[0] == "requested"]
        self.assertEqual([("requested", "A"), ("requested", "A")], requested)

    def test_failed_build_still_starts_cooldown(self):
        w = RecordingWorker()
        w.fail_builds = True
        w.request("A")
        w.run_until_idle()
        w.clock.advance(5)
        with self.assertLogs("ScheduleAgent", level="ERROR"):
            w.request("A")
        w.run_until_idle()
        self.assertEqual([("requested", "A")], w.builds())

    def test_station_without_schedule_is_skipped(self):
        w = RecordingWorker()
        w.request("Web")
        w.request("Nobody")
        w.run_until_idle()
        self.assertEqual([], w.builds())


class TopUpTests(unittest.TestCase):
    def test_no_topups_before_first_play(self):
        w = RecordingWorker()
        self.assertFalse(w.has_work())
        w.run_until_idle()
        self.assertEqual([], w.calls)

    def test_topups_one_station_per_step_after_first_play(self):
        w = RecordingWorker()
        w.handle_message(("first_play",))
        w.run_until_idle()
        self.assertEqual(
            [("prune",), ("check",), ("topup", "A", "week"), ("topup", "B", "week"), ("topup", "C", "week")],
            w.calls,
        )

    def test_topups_start_after_fallback_without_first_play(self):
        w = RecordingWorker()
        w.clock.advance(FIRST_PLAY_FALLBACK)
        w.run_until_idle()
        self.assertIn(("check",), w.calls)

    def test_request_jumps_ahead_of_remaining_topups(self):
        w = RecordingWorker()
        w.handle_message(("first_play",))
        w.step()  # check
        w.step()  # top up A
        w.request("E")
        w.run_until_idle()
        self.assertEqual(
            [("topup", "A", "week"), ("requested", "E"), ("topup", "B", "week"), ("topup", "C", "week")],
            w.builds(),
        )

    def test_check_repeats_hourly(self):
        w = RecordingWorker(needing_topup=())
        w.handle_message(("first_play",))
        w.run_until_idle()
        w.clock.advance(CHECK_INTERVAL - 1)
        self.assertFalse(w.has_work())
        w.clock.advance(1)
        w.run_until_idle()
        self.assertEqual(2, w.calls.count(("check",)))

    def test_unconfigured_agent_prunes_but_never_tops_up(self):
        w = RecordingWorker(conf=None)
        w.handle_message(("first_play",))
        w.run_until_idle()
        self.assertEqual([("prune",)], w.calls)
        w.request("A")
        w.run_until_idle()
        self.assertEqual([("requested", "A")], w.builds())


class FakeQueue:
    def __init__(self, messages):
        self.messages = list(messages)

    def get_nowait(self):
        if not self.messages:
            raise Empty
        return self.messages.pop(0)

    def get(self, timeout=None):
        return self.get_nowait()


class RunLoopTests(unittest.TestCase):
    def test_run_works_through_requests_and_stops(self):
        w = RecordingWorker()

        class StopWhenIdle(FakeQueue):
            def get(self, timeout=None):
                if not self.messages:
                    return ("stop",)
                return self.get_nowait()

        w.run(StopWhenIdle([("build", "A", w.clock()), ("build", "B", w.clock())]))
        self.assertEqual([("requested", "A"), ("requested", "B")], w.builds())


if __name__ == "__main__":
    unittest.main()
