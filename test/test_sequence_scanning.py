

import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out heavy / native deps BEFORE any fs42 import so the module-level
# guard in media_processor.py ("ffmpeg-python not found") does not abort.
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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.media_processor import MediaProcessor  # noqa: E402
from fs42.sequence_api import SequenceAPI  # noqa: E402
from fs42.sequence import NamedSequence  # noqa: E402


def _touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "a").close()
    return path


class ScanFixtureMixin:
    """
    Builds a content library that exercises the awkward cases:

        lib/ShowA/Season 01/ep1.mp4      normal, one season deep
        lib/ShowA/Season 01/._ep1.mp4    appledouble sidecar - not media
        lib/ShowA/.DS_Store              dotfile - not media
        lib/ShowB/ep1.MKV                uppercase extension
        lib/ShowB/.hidden.mp4            dotfile with a media extension
        lib/.hidden_dir/ep1.mp4          media inside a hidden directory
        lib/ShowLinked -> external/ShowC symlinked show outside the tree
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "lib")
        self.external = os.path.join(self.tmp, "external")

        _touch(self.lib, "ShowA", "Season 01", "ep1.mp4")
        _touch(self.lib, "ShowA", "Season 01", "._ep1.mp4")
        _touch(self.lib, "ShowA", ".DS_Store")
        _touch(self.lib, "ShowB", "ep1.MKV")
        _touch(self.lib, "ShowB", ".hidden.mp4")
        _touch(self.lib, ".hidden_dir", "ep1.mp4")
        _touch(self.external, "ShowC", "Season 02", "ep1.mp4")

        os.symlink(
            os.path.join("..", "external", "ShowC"),
            os.path.join(self.lib, "ShowLinked"),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def relative(self, paths):
        return sorted(os.path.relpath(p, self.lib) for p in paths)


class TestRfindMedia(ScanFixtureMixin, unittest.TestCase):
    def test_finds_nested_and_mixed_case_media(self):
        found = self.relative(MediaProcessor._rfind_media(self.lib))
        self.assertIn(os.path.join("ShowA", "Season 01", "ep1.mp4"), found)
        self.assertIn(os.path.join("ShowB", "ep1.MKV"), found)

    def test_skips_appledouble_sidecars(self):
        found = self.relative(MediaProcessor._rfind_media(self.lib))
        self.assertNotIn(os.path.join("ShowA", "Season 01", "._ep1.mp4"), found)

    def test_skips_dotfiles_and_hidden_dirs(self):
        found = self.relative(MediaProcessor._rfind_media(self.lib))
        self.assertNotIn(os.path.join("ShowB", ".hidden.mp4"), found)
        self.assertNotIn(os.path.join(".hidden_dir", "ep1.mp4"), found)
        self.assertFalse([p for p in found if os.path.basename(p).startswith(".")])

    def test_follows_symlinked_directories(self):
        found = self.relative(MediaProcessor._rfind_media(self.lib))
        self.assertIn(os.path.join("ShowLinked", "Season 02", "ep1.mp4"), found)

    def test_audio_filter_excludes_video(self):
        _touch(self.lib, "ShowB", "theme.mp3")
        found = self.relative(MediaProcessor._rfind_media(self.lib, "audio"))
        self.assertEqual(found, [os.path.join("ShowB", "theme.mp3")])


class TestFindShowDirs(ScanFixtureMixin, unittest.TestCase):
    def test_collapses_season_folders_to_show_root(self):
        shows = self.relative(SequenceAPI._find_show_dirs(self.lib))
        self.assertIn("ShowA", shows)
        self.assertNotIn(os.path.join("ShowA", "Season 01"), shows)

    def test_finds_show_with_media_at_top_level(self):
        shows = self.relative(SequenceAPI._find_show_dirs(self.lib))
        self.assertIn("ShowB", shows)

    def test_hidden_dir_is_not_a_show(self):
        shows = self.relative(SequenceAPI._find_show_dirs(self.lib))
        self.assertNotIn(".hidden_dir", shows)

    def test_symlinked_show_is_found(self):
        shows = self.relative(SequenceAPI._find_show_dirs(self.lib))
        self.assertIn("ShowLinked", shows)

    def test_dotfile_only_dir_is_not_a_show(self):
        _touch(self.lib, "ShowD", "._ep1.mp4")
        shows = self.relative(SequenceAPI._find_show_dirs(self.lib))
        self.assertNotIn("ShowD", shows)


class TestPutSequence(unittest.TestCase):
    """
    put_sequence upserts on (station, sequence_name, tag_path). Re-writing the
    same sequence must reuse the row id and replace its entries rather than
    minting a new id and orphaning the old ones.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

        patcher = patch("fs42.sequence_io.StationManager")
        station_manager = patcher.start()
        station_manager.return_value.server_conf = {"db_path": self.db_path}
        self.addCleanup(patcher.stop)

        from fs42.sequence_io import SequenceIO

        self.sio = SequenceIO()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _row_id(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute(
                "SELECT id FROM named_sequence WHERE station=? AND sequence_name=? AND tag_path=?",
                ("stn", "seq", "tag"),
            ).fetchone()[0]
        finally:
            connection.close()

    def _entry_count(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute("SELECT COUNT(*) FROM sequence_entries").fetchone()[0]
        finally:
            connection.close()

    def _put(self, files):
        self.sio.put_sequence("stn", NamedSequence("stn", "seq", "tag", 0.0, 1.0, 0, files))

    def test_reput_keeps_stable_row_id(self):
        self._put(["/m/a.mp4", "/m/b.mp4"])
        first = self._row_id()
        self._put(["/m/a.mp4", "/m/b.mp4"])
        self.assertEqual(first, self._row_id())

    def test_reput_does_not_duplicate_entries(self):
        self._put(["/m/a.mp4", "/m/b.mp4"])
        self._put(["/m/a.mp4", "/m/b.mp4"])
        self.assertEqual(self._entry_count(), 2)

    def test_reput_replaces_entries_with_new_content(self):
        self._put(["/m/a.mp4", "/m/b.mp4"])
        self._put(["/m/c.mp4"])
        self.assertEqual(self._entry_count(), 1)
        stored = self.sio.get_sequence("stn", "seq", "tag")
        self.assertEqual([e.fpath for e in stored.episodes], ["/m/c.mp4"])

    def test_reput_leaves_no_orphaned_entries(self):
        self._put(["/m/a.mp4", "/m/b.mp4"])
        self._put(["/m/c.mp4"])
        connection = sqlite3.connect(self.db_path)
        try:
            orphans = connection.execute(
                """SELECT COUNT(*) FROM sequence_entries
                   WHERE NOT EXISTS (
                       SELECT 1 FROM named_sequence
                       WHERE named_sequence.id = sequence_entries.named_sequence_id
                   )"""
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(orphans, 0)


if __name__ == "__main__":
    unittest.main()