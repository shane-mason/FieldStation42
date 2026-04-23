"""
Tests for the cross-channel sibling exclusion logic.

The feature prevents channels that share the same content_dir (e.g. Comedy1,
Comedy2, Comedy3) from scheduling the same movie at overlapping times — both
the "exact same start" case and the "starts halfway through" case.

Key pieces under test
---------------------
1. Overlap detection math  (inline in find_candidate, tested in isolation)
2. find_candidate exclusion filtering  (catalog.py)
3. _register_exclusion static method  (liquid_schedule.py)
4. _build_exclusion_index method  (liquid_schedule.py)

Running
-------
    # without pytest (stdlib only):
    python3 -m unittest test.test_exclusion -v

    # with pytest:
    python3 -m pytest test/test_exclusion.py -v
"""

import sys
import os
import datetime
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out heavy / native deps BEFORE any fs42 import so the module-level
# guard in media_processor.py ("ffmpeg-python not found") does not abort.
# MagicMock satisfies `hasattr(ffmpeg, 'probe')` automatically.
# ---------------------------------------------------------------------------
_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

# ---------------------------------------------------------------------------
# Safe to import fs42 now
# ---------------------------------------------------------------------------
from fs42.catalog_entry import CatalogEntry, MatchingContentNotFound  # noqa: E402
from fs42.liquid_blocks import LiquidBlock                             # noqa: E402


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

# A stable timeline for every test: Mon 1 Jan 2025
T20 = datetime.datetime(2025, 1, 1, 20, 0, 0)   # 20:00
T21 = datetime.datetime(2025, 1, 1, 21, 0, 0)   # 21:00
T22 = datetime.datetime(2025, 1, 1, 22, 0, 0)   # 22:00
T23 = datetime.datetime(2025, 1, 1, 23, 0, 0)   # 23:00

MOVIE_A = "/content/comedy/movie_a.mp4"
MOVIE_B = "/content/comedy/movie_b.mp4"
MOVIE_C = "/content/comedy/movie_c.mp4"
CONTENT_DIR = "/content"

NINETY_MIN = 90 * 60   # 5400 seconds


def _entry(path, duration=NINETY_MIN, count=0):
    """Build a CatalogEntry without touching the database."""
    e = CatalogEntry(path, duration, "comedy")
    e.realpath = os.path.realpath(path)
    e.count = count
    e.dbid = 1
    return e


def _block(content, start, end):
    """Build a minimal mock LiquidBlock."""
    b = MagicMock(spec=LiquidBlock)
    b.content = content
    b.start_time = start
    b.end_time = end
    return b


def _catalog(entries, network_name="Comedy1"):
    """Return a ShowCatalog with a hand-built clip_index, bypassing the DB."""
    from fs42.catalog import ShowCatalog
    conf = {
        "network_name": network_name,
        "network_type": "standard",
        "content_dir": CONTENT_DIR,
        "clip_shows": {},
        "break_strategy": "standard",
        "break_duration": 120,
        "commercial_free": True,
        "bump_dir": "bump",
        "schedule_increment": 30,
    }
    cat = ShowCatalog(conf, load=False)
    cat.clip_index = {"comedy": list(entries)}
    return cat


# ---------------------------------------------------------------------------
# 1.  Overlap detection math
#     The logic lives inline inside find_candidate.  We replicate it here so
#     it can be exercised exhaustively without requiring a full catalog.
# ---------------------------------------------------------------------------

class TestOverlapLogic(unittest.TestCase):
    """Verify the time-window overlap predicate used inside find_candidate."""

    @staticmethod
    def _overlaps(windows, proposed_start, duration_seconds):
        proposed_end = proposed_start + datetime.timedelta(seconds=duration_seconds)
        return any(
            proposed_start < w_end and w_start < proposed_end
            for w_start, w_end in windows
        )

    def test_exact_same_window(self):
        """Proposed window identical to an existing window → overlap."""
        self.assertTrue(self._overlaps([(T20, T22)], T20, NINETY_MIN * 2))

    def test_starts_inside_existing_window(self):
        """We start 1 h into a sibling's 2-h movie → overlap (the half-through case)."""
        self.assertTrue(self._overlaps([(T20, T22)], T21, NINETY_MIN))

    def test_ends_inside_existing_window(self):
        """Our movie starts before the sibling's but ends during it → overlap."""
        self.assertTrue(self._overlaps([(T21, T23)], T20, NINETY_MIN * 2))

    def test_contains_existing_window(self):
        """Our window completely contains the sibling's window → overlap."""
        self.assertTrue(self._overlaps([(T21, T22)], T20, 3 * 3600))

    def test_adjacent_before_no_overlap(self):
        """Our movie ends exactly when the sibling's starts → NOT an overlap."""
        # us: 20:00 + 2 h → ends 22:00 exactly; sibling: 22:00 – 23:00
        self.assertFalse(self._overlaps([(T22, T23)], T20, 2 * 3600))

    def test_adjacent_after_no_overlap(self):
        """Our movie starts exactly when the sibling's ends → NOT an overlap."""
        # sibling: 20:00 – 21:00; us: starts 21:00 for 2 h
        self.assertFalse(self._overlaps([(T20, T21)], T21, 2 * 3600))

    def test_completely_before_no_overlap(self):
        self.assertFalse(self._overlaps([(T22, T23)], T20, NINETY_MIN))

    def test_completely_after_no_overlap(self):
        self.assertFalse(self._overlaps([(T20, T21)], T22, NINETY_MIN))

    def test_empty_window_list(self):
        self.assertFalse(self._overlaps([], T20, NINETY_MIN))

    def test_multiple_windows_one_hits(self):
        windows = [
            (datetime.datetime(2025, 1, 1, 10, 0), datetime.datetime(2025, 1, 1, 12, 0)),
            (T20, T22),   # this one overlaps with T21 + 90 min
        ]
        self.assertTrue(self._overlaps(windows, T21, NINETY_MIN))

    def test_multiple_windows_none_hit(self):
        windows = [
            (datetime.datetime(2025, 1, 1, 10, 0), datetime.datetime(2025, 1, 1, 12, 0)),
            (datetime.datetime(2025, 1, 1, 14, 0), datetime.datetime(2025, 1, 1, 16, 0)),
        ]
        self.assertFalse(self._overlaps(windows, T20, NINETY_MIN))


# ---------------------------------------------------------------------------
# 2.  find_candidate exclusion filtering
# ---------------------------------------------------------------------------

class TestFindCandidateExclusion(unittest.TestCase):

    def test_no_exclusion_picks_lowest_count(self):
        """Baseline: no exclusion_index → lowest-count candidate wins."""
        a = _entry(MOVIE_A, count=2)
        b = _entry(MOVIE_B, count=0)   # lowest → wins
        c = _entry(MOVIE_C, count=1)
        cat = _catalog([a, b, c])

        result = cat.find_candidate("comedy", 99999, T20)
        self.assertEqual(result.path, MOVIE_B)

    def test_excluded_candidate_skipped(self):
        """Movie A is on a sibling right now — we must not pick it."""
        a = _entry(MOVIE_A, count=0)   # would win without exclusion
        b = _entry(MOVIE_B, count=0)
        c = _entry(MOVIE_C, count=1)
        cat = _catalog([a, b, c])

        exclusion_index = {
            os.path.realpath(MOVIE_A): [(T20, T20 + datetime.timedelta(seconds=NINETY_MIN))]
        }
        result = cat.find_candidate(
            "comedy", 99999, T20,
            exclusion_index=exclusion_index,
            proposed_start=T20,
        )
        self.assertNotEqual(result.path, MOVIE_A)

    def test_mid_play_overlap_is_blocked(self):
        """
        Sibling started Movie A 45 min ago and is still playing.
        We would launch it at the same wall-clock moment — should be blocked.
        """
        a = _entry(MOVIE_A, count=0)
        b = _entry(MOVIE_B, count=0)
        cat = _catalog([a, b])

        sibling_start = T20 - datetime.timedelta(minutes=45)
        sibling_end   = T20 + datetime.timedelta(minutes=45)
        exclusion_index = {
            os.path.realpath(MOVIE_A): [(sibling_start, sibling_end)]
        }
        result = cat.find_candidate(
            "comedy", 99999, T20,
            exclusion_index=exclusion_index,
            proposed_start=T20,
        )
        self.assertNotEqual(result.path, MOVIE_A)

    def test_finished_window_is_allowed(self):
        """
        Sibling played Movie A earlier in the day; it has finished.
        Movie A should be available again (lowest count wins).
        """
        a = _entry(MOVIE_A, count=0)   # lowest count
        b = _entry(MOVIE_B, count=1)
        cat = _catalog([a, b])

        # sibling played it 14:00 – 16:00; we're scheduling at 20:00
        past = (datetime.datetime(2025, 1, 1, 14, 0), datetime.datetime(2025, 1, 1, 16, 0))
        exclusion_index = {os.path.realpath(MOVIE_A): [past]}

        result = cat.find_candidate(
            "comedy", 99999, T20,
            exclusion_index=exclusion_index,
            proposed_start=T20,
        )
        self.assertEqual(result.path, MOVIE_A)

    def test_all_candidates_excluded_raises(self):
        """When every candidate is blocked, MatchingContentNotFound is raised."""
        entries = [_entry(p) for p in (MOVIE_A, MOVIE_B, MOVIE_C)]
        cat = _catalog(entries)

        window = (T20, T20 + datetime.timedelta(seconds=NINETY_MIN))
        exclusion_index = {
            os.path.realpath(MOVIE_A): [window],
            os.path.realpath(MOVIE_B): [window],
            os.path.realpath(MOVIE_C): [window],
        }
        with self.assertRaises(MatchingContentNotFound):
            cat.find_candidate(
                "comedy", 99999, T20,
                exclusion_index=exclusion_index,
                proposed_start=T20,
            )

    def test_none_realpath_is_not_excluded(self):
        """
        If a CatalogEntry has no realpath (shouldn't happen in practice but
        could on an edge-case entry), it is not excluded — it competes normally.
        """
        a = _entry(MOVIE_A, count=0)
        a.realpath = None   # simulate missing realpath
        cat = _catalog([a])

        # Even with a matching key in the exclusion index, realpath=None means
        # the guard is skipped and the entry is a valid candidate.
        exclusion_index = {None: [(T20, T22)]}  # key is None — won't match guard
        result = cat.find_candidate(
            "comedy", 99999, T20,
            exclusion_index=exclusion_index,
            proposed_start=T20,
        )
        self.assertEqual(result.path, MOVIE_A)

    def test_no_proposed_start_disables_check(self):
        """
        exclusion_index without proposed_start → check is bypassed entirely.
        Backwards-compatible: callers that don't pass proposed_start are unaffected.
        """
        a = _entry(MOVIE_A, count=0)
        cat = _catalog([a])

        # Even though the exclusion_index marks the window, no proposed_start
        # means we skip the check.
        exclusion_index = {
            os.path.realpath(MOVIE_A): [(T20, T22)]
        }
        result = cat.find_candidate(
            "comedy", 99999, T20,
            exclusion_index=exclusion_index,
            # proposed_start intentionally omitted
        )
        self.assertEqual(result.path, MOVIE_A)


# ---------------------------------------------------------------------------
# 3.  _register_exclusion  (static method — no mocking required)
# ---------------------------------------------------------------------------

class TestRegisterExclusion(unittest.TestCase):

    @staticmethod
    def _register():
        from fs42.liquid_schedule import LiquidSchedule
        return LiquidSchedule._register_exclusion

    def test_adds_new_key(self):
        reg = self._register()
        index = {}
        content = MagicMock()
        content.realpath = MOVIE_A
        block = MagicMock()
        block.content = content
        block.start_time = T20
        block.end_time = T22

        reg(index, block)

        self.assertIn(MOVIE_A, index)
        self.assertEqual(index[MOVIE_A], [(T20, T22)])

    def test_appends_second_window_for_same_path(self):
        reg = self._register()
        index = {MOVIE_A: [(T20, T21)]}
        content = MagicMock()
        content.realpath = MOVIE_A
        block = MagicMock()
        block.content = content
        block.start_time = T22
        block.end_time = T23

        reg(index, block)

        self.assertEqual(len(index[MOVIE_A]), 2)
        self.assertIn((T22, T23), index[MOVIE_A])

    def test_list_content_ignored(self):
        """Clip blocks hold a list of entries — they must not be indexed."""
        reg = self._register()
        index = {}
        block = MagicMock()
        block.content = [MagicMock(), MagicMock()]

        reg(index, block)

        self.assertEqual(index, {})

    def test_none_content_ignored(self):
        reg = self._register()
        index = {}
        block = MagicMock()
        block.content = None

        reg(index, block)

        self.assertEqual(index, {})

    def test_none_realpath_ignored(self):
        reg = self._register()
        index = {}
        content = MagicMock()
        content.realpath = None
        block = MagicMock()
        block.content = content

        reg(index, block)

        self.assertEqual(index, {})

    def test_index_not_mutated_for_off_air(self):
        """Off-air blocks have no content — index stays empty."""
        reg = self._register()
        index = {}
        block = MagicMock()
        block.content = None

        reg(index, block)

        self.assertEqual(index, {})


# ---------------------------------------------------------------------------
# 4.  _build_exclusion_index  (StationManager + LiquidIO mocked)
# ---------------------------------------------------------------------------

class TestBuildExclusionIndex(unittest.TestCase):

    def _make_schedule(self):
        """Return a bare LiquidSchedule instance, bypassing DB and file I/O."""
        conf = {
            "network_name": "Comedy1",
            "network_type": "standard",
            "content_dir": CONTENT_DIR,
            "clip_shows": {},
            "break_strategy": "standard",
            "break_duration": 120,
            "commercial_free": True,
            "bump_dir": "bump",
            "schedule_increment": 30,
            "monday": {"0": {"tags": "comedy"}},
        }
        with patch("fs42.liquid_schedule.StationManager"), \
             patch("fs42.liquid_schedule.LiquidIO"), \
             patch("fs42.liquid_schedule.LiquidAPI"), \
             patch("fs42.catalog.CatalogAPI"):
            from fs42.liquid_schedule import LiquidSchedule
            sched = LiquidSchedule.__new__(LiquidSchedule)
            sched.conf = conf
            import logging
            sched._l = logging.getLogger("test-exclusion")
        return sched

    def _sibling_conf(self, name="Comedy2", content_dir=CONTENT_DIR, tag="comedy"):
        return {
            "network_name": name,
            "network_type": "standard",
            "content_dir": content_dir,
            "monday": {"0": {"tags": tag}},
        }

    # ---- helpers shared across sub-tests ----

    def test_no_siblings_returns_empty_dict(self):
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
        ]
        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations

            result = sched._build_exclusion_index(T20, T22)

        self.assertEqual(result, {})
        MockIO.return_value.query_liquid_blocks.assert_not_called()

    def test_sibling_blocks_populate_index(self):
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
            self._sibling_conf("Comedy2"),
        ]
        rp = os.path.realpath(MOVIE_A)
        content = MagicMock()
        content.realpath = rp
        mock_block = _block(content, T20, T22)

        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations
            MockIO.return_value.query_liquid_blocks.return_value = [mock_block]

            result = sched._build_exclusion_index(T20, T22)

        self.assertIn(rp, result)
        self.assertEqual(result[rp], [(T20, T22)])

    def test_multiple_siblings_all_queried(self):
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
            self._sibling_conf("Comedy2"),
            self._sibling_conf("Comedy3"),
            self._sibling_conf("Comedy4"),
        ]
        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations
            MockIO.return_value.query_liquid_blocks.return_value = []

            sched._build_exclusion_index(T20, T22)

        # Should have been called once per sibling (3 times)
        self.assertEqual(MockIO.return_value.query_liquid_blocks.call_count, 3)

    def test_different_content_dir_not_a_sibling(self):
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
            self._sibling_conf("Sports1", content_dir="/other/content"),
        ]
        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations

            result = sched._build_exclusion_index(T20, T22)

        self.assertEqual(result, {})
        MockIO.return_value.query_liquid_blocks.assert_not_called()

    def test_same_content_dir_different_tags_not_a_sibling(self):
        """Drama channel shares content_dir with Comedy but uses a different tag.
        It can never schedule comedy files so it must not be treated as a sibling."""
        sched = self._make_schedule()  # Comedy1, tag=comedy

        # Drama channel: same content_dir, different tag
        drama_conf = {
            "network_name": "Drama1",
            "network_type": "standard",
            "content_dir": CONTENT_DIR,
            "monday": {"0": {"tags": "drama"}},
        }
        stations = [
            {"network_name": "Comedy1", "network_type": "standard",
             "content_dir": CONTENT_DIR, "monday": {"0": {"tags": "comedy"}}},
            drama_conf,
        ]
        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations

            result = sched._build_exclusion_index(T20, T22)

        self.assertEqual(result, {})
        MockIO.return_value.query_liquid_blocks.assert_not_called()

    def test_same_content_dir_same_tag_is_sibling(self):
        """Two comedy channels sharing both content_dir and tag are genuine siblings."""
        sched = self._make_schedule()  # Comedy1, tag=comedy

        comedy2_conf = {
            "network_name": "Comedy2",
            "network_type": "standard",
            "content_dir": CONTENT_DIR,
            "monday": {"0": {"tags": "comedy"}},
        }
        stations = [
            {"network_name": "Comedy1", "network_type": "standard",
             "content_dir": CONTENT_DIR, "monday": {"0": {"tags": "comedy"}}},
            comedy2_conf,
        ]
        rp = os.path.realpath(MOVIE_A)
        content = MagicMock()
        content.realpath = rp
        mock_block = _block(content, T20, T22)

        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations
            MockIO.return_value.query_liquid_blocks.return_value = [mock_block]

            result = sched._build_exclusion_index(T20, T22)

        self.assertIn(rp, result)

    def test_list_content_blocks_skipped(self):
        """Clip blocks (list content) must not appear in the exclusion index."""
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
            self._sibling_conf("Comedy2"),
        ]
        list_block = _block([MagicMock(), MagicMock()], T20, T22)  # clip show

        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations
            MockIO.return_value.query_liquid_blocks.return_value = [list_block]

            result = sched._build_exclusion_index(T20, T22)

        self.assertEqual(result, {})

    def test_exception_returns_empty_gracefully(self):
        """DB or IO errors during index build degrade gracefully — the scheduler
        continues without exclusion protection rather than crashing.  Logic errors
        (TypeError, AttributeError etc.) are NOT caught and will still propagate."""
        sched = self._make_schedule()

        with patch("fs42.liquid_schedule.StationManager") as MockSM:
            import sqlite3
            MockSM.side_effect = sqlite3.OperationalError("unable to open database")
            result = sched._build_exclusion_index(T20, T22)

        self.assertEqual(result, {})

    def test_query_called_with_correct_time_range(self):
        """Verify query_liquid_blocks receives space-separated datetime strings
        matching SQLite storage format (not isoformat T-separator strings, which
        would break same-day comparisons due to ASCII ordering: ' ' < 'T')."""
        sched = self._make_schedule()
        stations = [
            {"network_name": "Comedy1", "network_type": "standard", "content_dir": CONTENT_DIR},
            self._sibling_conf("Comedy2"),
        ]
        with patch("fs42.liquid_schedule.StationManager") as MockSM, \
             patch("fs42.liquid_schedule.LiquidIO") as MockIO:
            MockSM.return_value.stations = stations
            MockIO.return_value.query_liquid_blocks.return_value = []

            sched._build_exclusion_index(T20, T22)

        MockIO.return_value.query_liquid_blocks.assert_called_once_with(
            "Comedy2",
            str(T20),
            str(T22),
        )


# ---------------------------------------------------------------------------
# 5.  _fill graceful degradation  (exclusion exhausts candidates → retry)
# ---------------------------------------------------------------------------

class TestFillGracefulDegradation(unittest.TestCase):
    """When sibling exclusion blocks every candidate, _fill must retry without
    the exclusion index, log a WARNING, and return a block rather than raising.
    Only a genuine content shortage (fails even without exclusion) should
    propagate the exception."""

    def _make_sched(self):
        """LiquidSchedule with a mocked catalog, bypassing DB and file I/O."""
        with patch("fs42.liquid_schedule.StationManager"), \
             patch("fs42.liquid_schedule.LiquidIO"), \
             patch("fs42.liquid_schedule.LiquidAPI"), \
             patch("fs42.catalog.CatalogAPI"):
            from fs42.liquid_schedule import LiquidSchedule
            sched = LiquidSchedule.__new__(LiquidSchedule)
            sched.conf = {
                "network_name": "Comedy1",
                "break_strategy": "standard",
                "schedule_increment": 30,
                "clip_shows": {},
                "content_dir": CONTENT_DIR,
                "tag_overrides": {},
            }
            import logging
            sched._l = logging.getLogger("test-fill")
        sched.catalog = MagicMock()
        return sched

    def _slot(self):
        return {"tags": "comedy"}

    def test_exclusion_fallback_returns_block_and_logs_warning(self):
        """
        First find_candidate call (with exclusion) raises MatchingContentNotFound.
        Second call (without exclusion) succeeds.  _fill must:
          - return a valid (block, next_mark) tuple
          - log a WARNING so operators know an overlap was unavoidable
          - call find_candidate exactly twice
        """
        from fs42.catalog_entry import MatchingContentNotFound
        from fs42.liquid_schedule import LiquidSchedule

        sched = self._make_sched()
        candidate = MagicMock()
        candidate.duration = NINETY_MIN
        candidate.title = "Test Movie"
        candidate.path = MOVIE_A
        candidate.realpath = os.path.realpath(MOVIE_A)

        sched.catalog.find_candidate.side_effect = [
            MatchingContentNotFound("all blocked by exclusion"),
            candidate,
        ]

        exclusion_index = {os.path.realpath(MOVIE_A): [(T20, T22)]}

        with patch("fs42.liquid_schedule.PathQuery") as MockPQ, \
             patch.object(sched, "_break_info", return_value=(
                 {"start_bump": None, "end_bump": None, "bump_dir": None,
                  "commercial_dir": None, "break_strategy": None, "increment": None},
                 "standard", 30
             )):
            MockPQ.match_any_from_base.return_value = None
            with self.assertLogs("test-fill", level="WARNING") as log_ctx:
                block, next_mark = sched._fill(self._slot(), "comedy", T20,
                                               exclusion_index=exclusion_index)

        self.assertIsNotNone(block)
        self.assertIsNotNone(next_mark)
        # Retried twice: first with exclusion, then without
        self.assertEqual(sched.catalog.find_candidate.call_count, 2)
        first_call_kwargs = sched.catalog.find_candidate.call_args_list[0][1]
        self.assertIsNotNone(first_call_kwargs.get("exclusion_index"))
        # Warning must be present in logs
        self.assertTrue(
            any("exclusion" in m.lower() or "overlap unavoidable" in m.lower()
                for m in log_ctx.output)
        )

    def test_genuine_content_shortage_propagates(self):
        """
        When find_candidate raises even WITHOUT the exclusion index, it is a
        genuine content shortage (not an exclusion side-effect).  The exception
        must propagate so the caller can decide how to handle it.
        """
        from fs42.catalog_entry import MatchingContentNotFound
        sched = self._make_sched()
        # Both calls fail — no content exists at all
        sched.catalog.find_candidate.side_effect = MatchingContentNotFound("no content")

        exclusion_index = {os.path.realpath(MOVIE_A): [(T20, T22)]}

        with patch("fs42.liquid_schedule.PathQuery"):
            with self.assertRaises(MatchingContentNotFound):
                sched._fill(self._slot(), "comedy", T20,
                            exclusion_index=exclusion_index)

    def test_no_exclusion_shortage_propagates_immediately(self):
        """
        When no exclusion_index is active and content is not found, the exception
        propagates on the first call without any retry — there is nothing to retry.
        """
        from fs42.catalog_entry import MatchingContentNotFound
        sched = self._make_sched()
        sched.catalog.find_candidate.side_effect = MatchingContentNotFound("no content")

        with patch("fs42.liquid_schedule.PathQuery"):
            with self.assertRaises(MatchingContentNotFound):
                sched._fill(self._slot(), "comedy", T20)  # no exclusion_index

        # Called only once — no retry when there was no exclusion active
        self.assertEqual(sched.catalog.find_candidate.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
