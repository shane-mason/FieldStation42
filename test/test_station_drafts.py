import json
import pytest
from unittest.mock import patch

from fs42.station_manager import StationManager, StationConfigError
from fs42.station_io import StationIO


def _write_station(confs_dir, filename, station_conf):
    path = confs_dir / filename
    path.write_text(json.dumps({"station_conf": station_conf}))
    return str(path)


def _station_io_for(confs_dir):
    """A StationIO pointed at a throwaway confs directory."""
    station_io = StationIO()
    station_io.confs_dir = f"{confs_dir}/"
    station_io.main_config_path = f"{confs_dir}/main_config.json"
    return station_io


def _complete_station(name, channel, content_dir):
    """A station config that loads cleanly."""
    return {
        "network_name": name,
        "channel_number": channel,
        "network_type": "standard",
        "schedule_increment": 30,
        "content_dir": content_dir,
        "day_templates": {"daily": {"0": {"tags": "anything"}}},
        "monday": "daily",
        "tuesday": "daily",
        "wednesday": "daily",
        "thursday": "daily",
        "friday": "daily",
        "saturday": "daily",
        "sunday": "daily",
    }


class TestDraftConfigsAreSkipped:
    """Unfinished station configs stay on disk and are skipped, not fatal.

    The editor saves work-in-progress configs with placeholder paths and
    missing schedules. Those must not take down the rest of the stations.
    """

    def setup_method(self):
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

    def _make_manager(self, confs_dir):
        station_io = _station_io_for(confs_dir)
        with patch("fs42.station_manager.StationIO", return_value=station_io):
            return StationManager()

    def test_missing_content_dir_skips_only_that_station(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        _write_station(tmp_path, "good.json", _complete_station("Good", 3, str(content)))
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))

        manager = self._make_manager(tmp_path)

        assert [s["network_name"] for s in manager.stations] == ["Good"]
        assert len(manager.skipped_stations) == 1
        assert manager.skipped_stations[0]["network_name"] == "Draft"
        assert "catalog/?" in manager.skipped_stations[0]["error"]

    def test_missing_schedule_skips_only_that_station(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        _write_station(tmp_path, "good.json", _complete_station("Good", 3, str(content)))
        # No weekday keys at all - what the blank editor template produces
        _write_station(tmp_path, "draft.json", {
            "network_name": "Draft",
            "channel_number": 4,
            "content_dir": str(content),
        })

        manager = self._make_manager(tmp_path)

        assert [s["network_name"] for s in manager.stations] == ["Good"]
        assert len(manager.skipped_stations) == 1
        assert manager.skipped_stations[0]["network_name"] == "Draft"
        assert "monday" in manager.skipped_stations[0]["error"]

    def test_draft_is_not_reachable_as_a_live_station(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))

        manager = self._make_manager(tmp_path)

        assert manager.station_by_name("Draft") is None
        assert manager.station_by_channel(4) is None

    def test_all_stations_drafts_is_not_fatal(self, tmp_path):
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))

        manager = self._make_manager(tmp_path)

        assert manager.stations == []
        assert len(manager.skipped_stations) == 1

    def test_failed_reload_keeps_previously_loaded_stations(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        _write_station(tmp_path, "good.json", _complete_station("Good", 3, str(content)))

        manager = self._make_manager(tmp_path)
        assert [s["network_name"] for s in manager.stations] == ["Good"]

        # A reload that blows up entirely must not empty the shared singleton
        with patch.object(StationIO, "load_and_process_all_stations", side_effect=OSError("disk gone")):
            with pytest.raises(StationConfigError):
                manager._reload_stations()

        assert [s["network_name"] for s in manager.stations] == ["Good"]
        assert manager.station_by_name("Good") is not None

    def test_indexes_point_at_smoothed_configs(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        conf = _complete_station("Good", 3, str(content))
        # Slot 0 has tags, later slots inherit them via smoothing
        conf["day_templates"]["daily"]["1"] = {"continued": True}
        _write_station(tmp_path, "good.json", conf)

        manager = self._make_manager(tmp_path)

        indexed = manager.station_by_name("Good")
        assert indexed is manager.stations[0]
        assert indexed["monday"]["1"]["tags"] == "anything"


class TestUniquenessUsesDisk:
    """Drafts hold their name and channel number while being edited."""

    def setup_method(self):
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

    def test_draft_reserves_channel_number(self, tmp_path):
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))
        station_io = _station_io_for(tmp_path)

        is_unique, msg = station_io._check_uniqueness(4, "Something Else")

        assert not is_unique
        assert "already used" in msg

    def test_draft_reserves_network_name(self, tmp_path):
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))
        station_io = _station_io_for(tmp_path)

        is_unique, msg = station_io._check_uniqueness(99, "Draft")

        assert not is_unique
        assert "already exists" in msg

    def test_updating_a_draft_does_not_conflict_with_itself(self, tmp_path):
        _write_station(tmp_path, "draft.json", _complete_station("Draft", 4, "catalog/?"))
        station_io = _station_io_for(tmp_path)

        is_unique, msg = station_io._check_uniqueness(4, "Draft", exclude_name="Draft")

        assert is_unique, msg
