import datetime as dt
import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from fs42.block_plan import BlockPlanEntry
from fs42.database import connect
from fs42.hometv import (
    Airing,
    HLSSessionManager,
    ScheduleResolver,
    UnsafeMediaPath,
)
from fs42.media_processor import MediaProcessor
from fs42.fs42_server.api.watch import (
    SessionRequest,
    channels as channel_endpoint,
    create_session as create_session_endpoint,
)
from fs42.fs42_server.api import build as build_api
from fs42.fs42_server.api.schedules import (
    _attach_meta,
    _episode_display,
    _movie_display,
)


class FakeManager:
    def __init__(self):
        self.stations = [{
            "channel_number": 42,
            "network_name": "Test TV",
            "_has_schedule": True,
            "_has_catalog": True,
            "hidden": False,
        }]


class FakeProcess:
    def __init__(self, command):
        self.command = command
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class ResolverTests(unittest.TestCase):
    def test_current_plan_item_and_offset_include_scheduler_skip(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as media:
            start = dt.datetime(2026, 7, 30, 12, 0)
            block = SimpleNamespace(
                start_time=start,
                end_time=start + dt.timedelta(minutes=10),
                title="Lunch Show",
                plan=[
                    BlockPlanEntry(media.name, skip=5, duration=120),
                    BlockPlanEntry(media.name, skip=30, duration=480),
                ],
            )
            entry = SimpleNamespace(path=media.name, realpath=os.path.realpath(media.name))
            with (
                patch("fs42.hometv.LiquidAPI.get_blocks", return_value=[block]),
                patch("fs42.hometv.CatalogAPI.get_entries", return_value=[entry]),
            ):
                airing = ScheduleResolver(FakeManager()).now(
                    "42", start + dt.timedelta(seconds=150)
                )
            self.assertEqual(airing.program_title, "Lunch Show")
            self.assertEqual(airing.offset, 60)
            self.assertEqual(airing.remaining, 450)
            self.assertEqual(airing.item_start, start + dt.timedelta(seconds=120))
            self.assertEqual(
                airing.public_dict(start + dt.timedelta(seconds=150))["item_end"],
                (start + dt.timedelta(seconds=600)).isoformat(),
            )

    def test_channel_name_and_number_select_same_station(self):
        resolver = ScheduleResolver(FakeManager())
        self.assertEqual(resolver.station("42")["network_name"], "Test TV")
        self.assertEqual(resolver.station("Test TV")["channel_number"], 42)

    def test_episode_display_uses_series_prefix_without_episode_code(self):
        display = _episode_display(
            "/media/SpongeBob SquarePants/Season 04/"
            "SpongeBob SquarePants S04E15ab Squidtastic Voyage.mp4"
        )
        self.assertEqual(display["display_title"], "Spongebob Squarepants")
        self.assertEqual(display["episode_title"], "Squidtastic Voyage")
        self.assertEqual(display["season"], 4)
        self.assertEqual(display["episode"], "15ab")

    def test_episode_display_uses_show_directory_when_filename_starts_with_code(self):
        display = _episode_display(
            "/media/King of the Hill (1997)/Season 01/"
            "S01E10 Keeping Up With Our Joneses.mkv"
        )
        self.assertEqual(display["display_title"], "King Of The Hill")
        self.assertEqual(display["episode_title"], "Keeping Up With Our Joneses")

    def test_guide_display_metadata_does_not_read_file_metadata(self):
        block = SimpleNamespace(
            content=SimpleNamespace(
                path="/media/King of the Hill/Season 01/S01E10 Episode.mkv"
            )
        )
        with patch("fs42.fs42_server.api.schedules.MetadataIO.read") as read:
            _attach_meta([block], read_meta=False)
        read.assert_not_called()
        self.assertEqual(block.display_title, "King Of The Hill")

    def test_movie_release_name_keeps_only_title_and_year(self):
        display = _movie_display(
            "/media/Movies/War Dogs 2016 2160p Hybrid UHD BluRay Remux DV HDR.mkv"
        )
        self.assertEqual(display["display_title"], "War Dogs (2016)")

    def test_movie_extra_uses_parent_movie_identity(self):
        display = _movie_display(
            "/media/Movies/War Dogs (2016)/Featurettes/"
            "'On Location Napoleon Dynamite' Documentary.mkv"
        )
        self.assertEqual(display["display_title"], "War Dogs (2016)")

    def test_guide_uses_known_english_series_alias(self):
        block = SimpleNamespace(
            title="Shingeki No Kyojin The Final Season",
            content=SimpleNamespace(path="/media/anime/Shingeki No Kyojin.mkv"),
        )
        _attach_meta([block], read_meta=False)
        self.assertEqual(block.display_title, "Attack on Titan")

    def test_episode_uses_known_english_series_alias(self):
        display = _episode_display(
            "/media/Shingeki No Kyojin/Season 04/"
            "Shingeki No Kyojin S04E01 The Other Side.mkv"
        )
        self.assertEqual(display["display_title"], "Attack on Titan")

    def test_recursive_scan_ignores_movie_auxiliary_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feature = root / "War Dogs (2016)" / "War Dogs (2016).mkv"
            extra = root / "War Dogs (2016)" / "Featurettes" / "Documentary.mkv"
            feature.parent.mkdir()
            extra.parent.mkdir()
            feature.touch()
            extra.touch()
            self.assertEqual(MediaProcessor._rfind_media(temp_dir), [str(feature)])

    def test_schedule_path_must_exist_in_catalog(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as media:
            with patch("fs42.hometv.CatalogAPI.get_entries", return_value=[]):
                with self.assertRaises(UnsafeMediaPath):
                    ScheduleResolver._approved_media_path(
                        FakeManager().stations[0], media.name
                    )


class SessionTests(unittest.TestCase):
    def test_session_command_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "show.mkv"
            media.touch()
            when = dt.datetime.now()
            airing = Airing(
                "42", "Test TV", "Show", "Episode", when,
                when + dt.timedelta(minutes=30), when,
                when + dt.timedelta(minutes=30), str(media), 91.25, 1800, 1708.75,
            )
            resolver = SimpleNamespace(now=lambda channel: airing)
            processes = []

            def factory(command, **_kwargs):
                process = FakeProcess(command)
                processes.append(process)
                return process

            manager = HLSSessionManager(
                resolver=resolver,
                root=Path(temp_dir) / "hls",
                process_factory=factory,
            )
            session, _ = manager.create("42")
            self.assertIn("-ss", processes[0].command)
            self.assertIn("-re", processes[0].command)
            self.assertIn("-t", processes[0].command)
            self.assertIn("-force_key_frames", processes[0].command)
            self.assertEqual(
                processes[0].command[
                    processes[0].command.index("-hls_list_size") + 1
                ],
                "12",
            )
            self.assertEqual(
                processes[0].command[processes[0].command.index("-ss") + 1],
                "91.250",
            )
            self.assertTrue(session.directory.is_dir())
            self.assertTrue(manager.delete(session.session_id))
            self.assertFalse(session.directory.exists())
            self.assertEqual(processes[0].returncode, 0)

    def test_non_english_audio_selects_english_subtitles(self):
        probe = SimpleNamespace(
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "audio",
                            "codec_name": "aac",
                            "tags": {"language": "jpn"},
                        },
                        {
                            "codec_type": "subtitle",
                            "codec_name": "ass",
                            "tags": {"language": "eng"},
                        },
                    ]
                }
            )
        )
        with patch("fs42.hometv.subprocess.run", return_value=probe):
            self.assertEqual(
                HLSSessionManager._english_subtitle("/media/show.mkv"),
                ("ass", 0),
            )

    def test_english_audio_does_not_enable_subtitles(self):
        probe = SimpleNamespace(
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "audio",
                            "tags": {"language": "eng"},
                        },
                        {
                            "codec_type": "subtitle",
                            "codec_name": "ass",
                            "tags": {"language": "eng"},
                        },
                    ]
                }
            )
        )
        with patch("fs42.hometv.subprocess.run", return_value=probe):
            self.assertIsNone(
                HLSSessionManager._english_subtitle("/media/show.mkv")
            )

    def test_auto_profile_burns_selected_text_subtitle(self):
        when = dt.datetime.now()
        airing = Airing(
            "42",
            "Anime",
            "Attack on Titan",
            "Episode",
            when,
            when + dt.timedelta(minutes=30),
            when,
            when + dt.timedelta(minutes=30),
            "/media/Attack on Titan's Return.mkv",
            30,
            1800,
            1770,
        )
        command = HLSSessionManager._ffmpeg_command(
            airing,
            "auto",
            Path("/tmp/hls"),
            ("ass", 0),
        )
        self.assertIn("-vf", command)
        subtitle_filter = command[command.index("-vf") + 1]
        self.assertIn("subtitles=", subtitle_filter)
        self.assertIn(r"Attack on Titan\'s Return.mkv", subtitle_filter)

    def test_hls_asset_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = HLSSessionManager(
                resolver=SimpleNamespace(),
                root=temp_dir,
                process_factory=lambda *_args, **_kwargs: None,
            )
            with self.assertRaises(ValueError):
                manager.asset("missing", "../secret")


class DatabaseTests(unittest.TestCase):
    def test_connections_enable_wal_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test.db")
            connection = connect(db_path)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA journal_mode").fetchone()[0].lower(),
                    "wal",
                )
                self.assertGreaterEqual(
                    connection.execute("PRAGMA busy_timeout").fetchone()[0], 1000
                )
            finally:
                connection.close()


class WatchAPITests(unittest.TestCase):
    def setUp(self):
        manager = SimpleNamespace(
            resolver=SimpleNamespace(
                channels=lambda: [{
                    "channel_number": "42",
                    "channel_name": "Test TV",
                }]
            ),
            create=lambda channel, profile: (_ for _ in ()).throw(
                ValueError("Unknown client profile")
            ),
        )
        self.request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(hls_sessions=manager))
        )

    def test_channel_list_does_not_expose_paths(self):
        response = asyncio.run(channel_endpoint(self.request))
        self.assertNotIn("path", str(response))

    def test_invalid_profile_returns_validation_error(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(create_session_endpoint(
                SessionRequest(channel="42", profile="unsupported"),
                self.request,
            ))
        self.assertEqual(raised.exception.status_code, 422)


class BuildOperationTests(unittest.TestCase):
    def tearDown(self):
        if build_api.operation_lock.locked():
            build_api.operation_lock.release()

    def test_overlapping_operation_is_rejected(self):
        build_api.operation_lock.acquire()
        with self.assertRaises(HTTPException) as raised:
            build_api._begin_operation()
        self.assertEqual(raised.exception.status_code, 409)

    def test_failed_rebuild_reaches_error_and_releases_lock(self):
        station = {
            "network_name": "Test TV",
            "_has_catalog": True,
            "_has_schedule": False,
        }
        manager = SimpleNamespace(
            stations=[station],
            station_by_name=lambda name: station if name == "Test TV" else None,
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(player_command_queue=None)
            )
        )
        with (
            patch("fs42.fs42_server.api.build.StationManager", return_value=manager),
            patch("fs42.fs42_server.api.build.CatalogAPI.delete_catalog"),
            patch(
                "fs42.fs42_server.api.build.ShowCatalog",
                side_effect=RuntimeError("forced rebuild failure"),
            ),
        ):
            response = asyncio.run(
                build_api.quick_action("rebuild", "Test TV", request)
            )
            task_id = response["task_id"]
            for _ in range(100):
                task = asyncio.run(build_api.quick_action_status(task_id))
                if task["status"] == "error":
                    break
                time.sleep(0.01)
        self.assertEqual(task["status"], "error")
        self.assertIn("forced rebuild failure", task["log"])
        self.assertTrue(build_api.operation_lock.acquire(blocking=False))

    def test_rebuild_and_week_generates_initial_schedule(self):
        station = {
            "network_name": "Test TV",
            "_has_catalog": True,
            "_has_schedule": False,
        }
        manager = SimpleNamespace(
            stations=[station],
            station_by_name=lambda name: station if name == "Test TV" else None,
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(player_command_queue=None)
            )
        )
        with (
            patch("fs42.fs42_server.api.build.StationManager", return_value=manager),
            patch("fs42.fs42_server.api.build.CatalogAPI.delete_catalog"),
            patch("fs42.fs42_server.api.build.ShowCatalog"),
            patch("fs42.fs42_server.api.build.LiquidManager.reload_schedules"),
            patch("fs42.fs42_server.api.build.LiquidSchedule") as schedule,
        ):
            response = asyncio.run(
                build_api.quick_action("rebuild_and_week", "Test TV", request)
            )
            for _ in range(100):
                task = asyncio.run(
                    build_api.quick_action_status(response["task_id"])
                )
                if task["status"] in {"done", "error"}:
                    break
                time.sleep(0.01)
        self.assertEqual(task["status"], "done")
        schedule.return_value.add_amount.assert_called_once_with("week")


if __name__ == "__main__":
    unittest.main()
