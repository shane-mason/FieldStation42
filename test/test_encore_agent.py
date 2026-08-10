import datetime
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

from fs42.catalog_entry import CatalogEntry
from fs42.encore_agent import EncoreAgent, EncoreUnavailable
from fs42.liquid_blocks import LiquidBlock
from fs42.sequence import NamedSequence
from fs42.sequence_api import SequenceAPI
from fs42.sequence_io import SequenceIO
from fs42.station_manager import StationManager


def _configure_db(tmp_path):
    manager = StationManager()
    manager.server_conf["db_path"] = os.path.join(tmp_path, "fs42.db")
    manager.server_conf["normalize_titles"] = False


def _entry(path, tag="prime"):
    entry = CatalogEntry(path, 60 * 60, tag)
    entry.realpath = os.path.realpath(path)
    return entry


class FakeCatalog:
    def __init__(self, entries):
        self.entries = {entry.path: entry for entry in entries}

    def entry_by_fpath(self, fpath):
        return self.entries.get(fpath)


def _block(entry, start):
    return LiquidBlock(
        entry,
        start,
        start + datetime.timedelta(hours=1),
        entry.title,
        "standard",
        {},
    )


def _agent(tmp_path, entries):
    _configure_db(tmp_path)
    conf = {
        "network_name": "TestTV",
        "content_dir": "/content",
        "clip_shows": {},
    }
    return EncoreAgent(conf, FakeCatalog(entries))


class TestEncoreAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def tmp_path(self):
        return self.tmp.name

    def test_offset_replay_uses_build_local_airing_without_sequence(self):
        mon18 = datetime.datetime(2026, 8, 3, 18)
        tue06 = datetime.datetime(2026, 8, 4, 6)
        e01 = _entry("/content/prime/show_a/e01.mp4")
        agent = _agent(self.tmp_path, [e01])

        agent.record_airing("prime1", _block(e01, mon18))

        candidate, key = agent.resolve(
            {"source": "prime1", "strategy": "offset", "offset": "12h"},
            tue06,
        )

        self.assertEqual(candidate.path, e01.path)
        self.assertEqual(key["source_start_time"], mon18.isoformat())

    def test_offset_missing_source_raises_for_fallback_path(self):
        agent = _agent(self.tmp_path, [])

        with self.assertRaises(EncoreUnavailable):
            agent.resolve(
                {"source": "prime1", "strategy": "offset", "offset": "12h"},
                datetime.datetime(2026, 8, 4, 6),
            )

    def test_offset_continued_progression_replays_prior_evening(self):
        mon18 = datetime.datetime(2026, 8, 3, 18)
        tue06 = datetime.datetime(2026, 8, 4, 6)
        tue18 = datetime.datetime(2026, 8, 4, 18)
        wed06 = datetime.datetime(2026, 8, 5, 6)
        entries = [_entry(f"/content/prime/show_a/e{i:02}.mp4") for i in range(1, 5)]
        agent = _agent(self.tmp_path, entries)

        for index, entry in enumerate(entries[:2]):
            agent.record_airing("prime1", _block(entry, mon18 + datetime.timedelta(hours=index)))
        tue_paths = [
            agent.resolve(
                {"source": "prime1", "strategy": "offset", "offset": "12h"},
                tue06 + datetime.timedelta(hours=index),
            )[0].path
            for index in range(2)
        ]

        for index, entry in enumerate(entries[2:]):
            agent.record_airing("prime1", _block(entry, tue18 + datetime.timedelta(hours=index)))
        wed_paths = [
            agent.resolve(
                {"source": "prime1", "strategy": "offset", "offset": "12h"},
                wed06 + datetime.timedelta(hours=index),
            )[0].path
            for index in range(2)
        ]

        self.assertEqual(tue_paths, [entries[0].path, entries[1].path])
        self.assertEqual(wed_paths, [entries[2].path, entries[3].path])

    def test_offset_replays_odd_show_boundary_and_seasonal_change(self):
        mon18 = datetime.datetime(2026, 9, 21, 18)
        tue06 = datetime.datetime(2026, 9, 22, 6)
        entries = [
            _entry("/content/summer/prime/show_a/e21.mp4", tag="summer/prime/show_a"),
            _entry("/content/autumn/prime/show_b/e01.mp4", tag="autumn/prime/show_b"),
        ]
        agent = _agent(self.tmp_path, entries)

        for index, entry in enumerate(entries):
            agent.record_airing("prime1", _block(entry, mon18 + datetime.timedelta(hours=index)))

        encore_paths = [
            agent.resolve(
                {"source": "prime1", "strategy": "offset", "offset": "12h"},
                tue06 + datetime.timedelta(hours=index),
            )[0].path
            for index in range(2)
        ]

        self.assertEqual(encore_paths, [entry.path for entry in entries])

    def test_queue_persists_progress_and_next_run_starts_after_consumed(self):
        start = datetime.datetime(2026, 8, 3, 18)
        entries = [_entry(f"/content/prime/show_a/e{i:02}.mp4") for i in range(1, 13)]
        agent = _agent(self.tmp_path, entries)
        for index, entry in enumerate(entries):
            agent.record_airing("prime1", _block(entry, start + datetime.timedelta(hours=index)))
        agent.commit()

        sunday = datetime.datetime(2026, 8, 9, 6)
        first_paths = []
        for _ in range(6):
            candidate, _key = agent.resolve(
                {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
                sunday,
            )
            first_paths.append(candidate.path)
        agent.commit()

        next_agent = _agent(self.tmp_path, entries)
        candidate, _key = next_agent.resolve(
            {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
            sunday + datetime.timedelta(days=7),
        )

        self.assertEqual(first_paths, [entry.path for entry in entries[:6]])
        self.assertEqual(candidate.path, entries[6].path)

    def test_queue_survives_show_change_by_consuming_history_order(self):
        start = datetime.datetime(2026, 8, 3, 18)
        entries = [
            _entry("/content/prime/show_a/e21.mp4"),
            _entry("/content/prime/show_a/e22.mp4"),
            _entry("/content/prime/show_b/e01.mp4"),
        ]
        agent = _agent(self.tmp_path, entries)
        for index, entry in enumerate(entries):
            agent.record_airing("prime1", _block(entry, start + datetime.timedelta(hours=index)))
        agent.commit()

        paths = []
        for _ in range(3):
            candidate, _key = agent.resolve(
                {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
                datetime.datetime(2026, 8, 9, 6),
            )
            paths.append(candidate.path)

        self.assertEqual(paths, [entry.path for entry in entries])

    def test_independent_queue_cursors_share_source_without_sharing_position(self):
        start = datetime.datetime(2026, 8, 3, 18)
        entries = [_entry(f"/content/prime/show_a/e{i:02}.mp4") for i in range(1, 4)]
        agent = _agent(self.tmp_path, entries)
        for index, entry in enumerate(entries):
            agent.record_airing("prime1", _block(entry, start + datetime.timedelta(hours=index)))
        agent.commit()

        a1, _ = agent.resolve(
            {"source": "prime1", "strategy": "queue", "cursor": "sunday_a"},
            datetime.datetime(2026, 8, 9, 6),
        )
        a2, _ = agent.resolve(
            {"source": "prime1", "strategy": "queue", "cursor": "sunday_a"},
            datetime.datetime(2026, 8, 9, 6),
        )
        b1, _ = agent.resolve(
            {"source": "prime1", "strategy": "queue", "cursor": "sunday_b"},
            datetime.datetime(2026, 8, 9, 6),
        )

        self.assertEqual([a1.path, a2.path], [entries[0].path, entries[1].path])
        self.assertEqual(b1.path, entries[0].path)

    def test_queue_does_not_replay_future_source_occurrences(self):
        entry = _entry("/content/prime/show_a/e01.mp4")
        agent = _agent(self.tmp_path, [entry])
        agent.record_airing("prime1", _block(entry, datetime.datetime(2026, 8, 9, 18)))

        with self.assertRaises(EncoreUnavailable):
            agent.resolve(
                {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
                datetime.datetime(2026, 8, 9, 6),
            )

    def test_reset_cursors_from_blocks_rewinds_deleted_future_encores(self):
        entries = [_entry(f"/content/prime/show_a/e{i:02}.mp4") for i in range(1, 8)]
        agent = _agent(self.tmp_path, entries)
        start = datetime.datetime(2026, 8, 3, 18)
        for index, entry in enumerate(entries):
            agent.record_airing("prime1", _block(entry, start + datetime.timedelta(hours=index)))
        agent.commit()

        sunday = datetime.datetime(2026, 8, 9, 6)
        future_blocks = []
        for _ in range(6):
            candidate, key = agent.resolve(
                {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
                sunday,
            )
            block = _block(candidate, sunday)
            block.encore_key = key
            future_blocks.append(block)
        agent.commit()

        conf = {"network_name": "TestTV", "content_dir": "/content", "clip_shows": {}}
        EncoreAgent.reset_cursors_from_blocks(
            conf,
            future_blocks,
            datetime.datetime(2026, 8, 9),
        )
        next_agent = _agent(self.tmp_path, entries)
        candidate, _key = next_agent.resolve(
            {"source": "prime1", "strategy": "queue", "cursor": "prime1_sunday"},
            datetime.datetime(2026, 8, 9, 6),
        )

        self.assertEqual(candidate.path, entries[0].path)

    def test_random_show_completed_child_rolls_to_another_child(self):
        _configure_db(self.tmp_path)
        conf = {"network_name": "TestTV"}
        sio = SequenceIO()
        sio.put_sequence(
            "TestTV",
            NamedSequence(
                "TestTV",
                "prime1",
                "prime/show_a",
                0,
                1,
                2,
                ["/content/prime/show_a/e01.mp4", "/content/prime/show_a/e02.mp4"],
                True,
            ),
        )
        sio.put_sequence(
            "TestTV",
            NamedSequence(
                "TestTV",
                "prime1",
                "prime/show_b",
                0,
                1,
                0,
                ["/content/prime/show_b/e01.mp4", "/content/prime/show_b/e02.mp4"],
                True,
            ),
        )
        sio.set_active_sequence("TestTV", "prime1", "prime", "prime/show_a")

        next_entry = SequenceAPI.get_next_in_sequence(conf, "prime1", "prime")

        self.assertEqual(next_entry.fpath, "/content/prime/show_b/e01.mp4")
        self.assertEqual(sio.get_active_sequence("TestTV", "prime1", "prime"), "prime/show_b")


if __name__ == "__main__":
    unittest.main()
