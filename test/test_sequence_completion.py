

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.sequence import NamedSequence  # noqa: E402
from fs42.sequence_api import SequenceAPI  # noqa: E402


def _seq(n_episodes, end_perc=1.0, start_perc=0.0, current_index=0):
    files = [f"/m/ep{i:02d}.mp4" for i in range(n_episodes)]
    return NamedSequence(
        "stn", "seq", "tag", start_perc, end_perc, current_index, files, initialized=True
    )


class TestNormalizeSequencePosition(unittest.TestCase):
    def test_index_at_episode_count_is_left_alone(self):
        # This is the end-of-sequence position - it must survive normalization
        # so get_next_in_sequence can act on it.
        seq = _seq(4, current_index=4)
        self.assertTrue(SequenceAPI._normalize_sequence_position(seq))
        self.assertEqual(seq.current_index, 4)

    def test_index_past_episode_count_wraps_to_zero(self):
        seq = _seq(4, current_index=9)
        self.assertTrue(SequenceAPI._normalize_sequence_position(seq))
        self.assertEqual(seq.current_index, 0)

    def test_index_below_negative_one_clamps(self):
        seq = _seq(4, current_index=-5)
        self.assertTrue(SequenceAPI._normalize_sequence_position(seq))
        self.assertEqual(seq.current_index, -1)

    def test_empty_sequence_returns_false(self):
        seq = _seq(0)
        self.assertFalse(SequenceAPI._normalize_sequence_position(seq))


class TestEndIndexClamp(unittest.TestCase):
    def test_end_perc_one_gives_full_length(self):
        self.assertEqual(_seq(4, end_perc=1.0).end_index, 4)

    def test_end_perc_over_one_is_clamped_to_length(self):
        self.assertEqual(_seq(4, end_perc=1.5).end_index, 4)

    def test_partial_end_perc_is_a_slice(self):
        self.assertEqual(_seq(4, end_perc=0.5).end_index, 2)


class TestStartIndex(unittest.TestCase):
    """
    start_index is derived from start_perc and must be recomputed on every load
    (initialized=True is the persisted-sequence case), not left at 0. Loop-back
    and reset land on start_index.
    """

    def test_recomputed_on_reload(self):
        # initialized=True simulates a sequence loaded back from the DB.
        self.assertEqual(_seq(4, start_perc=0.5, current_index=3).start_index, 2)

    def test_first_init_seeds_current_index_to_start(self):
        seq = NamedSequence(
            "stn", "seq", "tag", 0.5, 1.0, 0,
            [f"/m/ep{i}.mp4" for i in range(4)], initialized=False,
        )
        self.assertEqual(seq.start_index, 2)
        self.assertEqual(seq.current_index, 2)

    def test_negative_start_perc_opens_window_at_zero(self):
        self.assertEqual(_seq(4, start_perc=-1.0).start_index, 0)

    def test_start_index_never_passes_the_last_playable_episode(self):
        # start_perc == end_perc == 1.0 would otherwise put start_index past the
        # end and strand the sequence with nothing to play.
        seq = _seq(4, start_perc=1.0, end_perc=1.0)
        self.assertEqual(seq.start_index, seq.end_index - 1)

    def test_loop_back_returns_to_start_index(self):
        # A childless sequence starting halfway through should loop back to the
        # halfway point, not to 0.
        files = [f"/m/ep{i}.mp4" for i in range(4)]
        seq = NamedSequence("stn", "seq", "tag", 0.5, 1.0, 3, files, initialized=True)
        seq.current_index = seq.end_index  # sitting at the end
        # mimic the loop-back branch of get_next_in_sequence
        self.assertTrue(SequenceAPI._normalize_sequence_position(seq))
        self.assertTrue(seq.current_index >= seq.end_index)
        seq.current_index = seq.start_index
        self.assertEqual(seq.current_index, 2)


class TestRandomShowRotation(unittest.TestCase):
    """
    End-to-end: a random_show-style parent with two child sequences must switch
    to the other child once the active one is exhausted, rather than replaying
    the same child forever.
    """

    STATION = {"network_name": "stn"}
    SEQ = "seq"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

        patcher = patch("fs42.sequence_io.StationManager")
        station_manager = patcher.start()
        station_manager.return_value.server_conf = {"db_path": self.db_path}
        self.addCleanup(patcher.stop)

        from fs42.sequence_io import SequenceIO

        self.sio = SequenceIO()

        self._put_child("shows/ShowA", ["/m/ShowA/a1.mp4", "/m/ShowA/a2.mp4"])
        self._put_child("shows/ShowB", ["/m/ShowB/b1.mp4", "/m/ShowB/b2.mp4"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put_child(self, tag_path, files):
        ns = NamedSequence("stn", self.SEQ, tag_path, 0.0, 1.0, 0, files, initialized=True)
        ns.parent_tag = "shows"
        self.sio.put_sequence("stn", ns)

    def _next_show(self):
        entry = SequenceAPI.get_next_in_sequence(self.STATION, self.SEQ, "shows")
        # /m/ShowA/a1.mp4 -> ShowA
        return entry.fpath.split("/")[2]

    def test_switches_child_after_active_one_is_exhausted(self):
        first = self._next_show()
        self.assertEqual(self._next_show(), first)  # still on the first show
        second = self._next_show()  # active child exhausted -> must rotate
        self.assertNotEqual(second, first)

    def test_does_not_lock_onto_one_show(self):
        seen = {self._next_show() for _ in range(8)}
        self.assertEqual(seen, {"ShowA", "ShowB"})


class TestChildlessLoopBack(unittest.TestCase):
    """
    End-to-end: a plain (no children) sequence configured with a start offset
    must loop back to that offset, not to 0, once it reaches the end.
    """

    STATION = {"network_name": "stn"}
    SEQ = "seq"
    TAG = "movies"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

        patcher = patch("fs42.sequence_io.StationManager")
        station_manager = patcher.start()
        station_manager.return_value.server_conf = {"db_path": self.db_path}
        self.addCleanup(patcher.stop)

        from fs42.sequence_io import SequenceIO

        self.sio = SequenceIO()

        files = [f"/m/ep{i}.mp4" for i in range(4)]
        # start_perc 0.5 over 4 episodes -> start_index 2
        self.sio.put_sequence(
            "stn", NamedSequence("stn", self.SEQ, self.TAG, 0.5, 1.0, 2, files, initialized=True)
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _next(self):
        return SequenceAPI.get_next_in_sequence(self.STATION, self.SEQ, self.TAG).fpath

    def test_loops_back_to_start_offset(self):
        played = [self._next() for _ in range(5)]
        # ep2, ep3, then loop back to the start offset (ep2) - never ep0/ep1
        self.assertEqual(
            played,
            ["/m/ep2.mp4", "/m/ep3.mp4", "/m/ep2.mp4", "/m/ep3.mp4", "/m/ep2.mp4"],
        )


if __name__ == "__main__":
    unittest.main()
