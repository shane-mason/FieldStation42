import datetime as dt
import asyncio
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
from fs42.fs42_server.api.watch import (
    SessionRequest,
    channels as channel_endpoint,
    create_session as create_session_endpoint,
)
from fs42.fs42_server.api import build as build_api


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
                processes[0].command[processes[0].command.index("-ss") + 1],
                "91.250",
            )
            self.assertTrue(session.directory.is_dir())
            self.assertTrue(manager.delete(session.session_id))
            self.assertFalse(session.directory.exists())
            self.assertEqual(processes[0].returncode, 0)

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
