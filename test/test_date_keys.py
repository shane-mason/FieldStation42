import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())

from fs42.config_processor import ConfigProcessor, ConfigurationError  # noqa: E402
from fs42.slot_reader import SlotReader  # noqa: E402


class TestDateKeyMatches:
    def test_single_day(self):
        assert SlotReader._date_key_matches("April 23", datetime(2026, 4, 23, 20, 0))
        assert not SlotReader._date_key_matches("April 23", datetime(2026, 4, 24, 20, 0))

    def test_same_year_range(self):
        assert SlotReader._date_key_matches("April 23 - April 25", datetime(2026, 4, 24))
        assert not SlotReader._date_key_matches("April 23 - April 25", datetime(2026, 4, 26))

    def test_wraparound_range(self):
        key = "December 24 - January 2"
        assert SlotReader._date_key_matches(key, datetime(2026, 12, 30))
        assert SlotReader._date_key_matches(key, datetime(2027, 1, 1))
        assert not SlotReader._date_key_matches(key, datetime(2027, 1, 3))

    def test_leap_day_uses_scheduled_year(self):
        assert SlotReader._date_key_matches("February 29", datetime(2028, 2, 29))
        assert not SlotReader._date_key_matches("February 29", datetime(2027, 3, 1))


class TestValidDateKey:
    def test_valid_keys(self):
        assert ConfigProcessor._valid_date_key("April 23")
        assert ConfigProcessor._valid_date_key("December 24 - January 2")

    def test_invalid_day_rejected(self):
        with pytest.raises(ConfigurationError):
            ConfigProcessor._valid_date_key("April 31")


@pytest.fixture
def holidays():
    from unittest.mock import patch

    from fs42.station_manager import StationManager
    from fs42.station_io import StationIO

    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    config_data = {"server_port": 4242, "custom_holidays": {
        "thanksgiving": "4th thursday november",
        "May Day": "May 1",
    }}
    with patch.object(StationIO, "load_main_config", return_value=config_data):
        with patch("fs42.station_io.glob.glob", return_value=[]):
            StationManager()
    yield
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []


def _conf(**extra):
    conf = {
        "network_name": "Test",
        "day_templates": {
            "normal": {"20": {"tags": "sitcoms"}, "21": {"tags": "drama"}},
            "holiday": {"8": {"tags": "parades"}, "9": {"continued": True}},
        },
    }
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        conf[day] = "normal"
    conf.update(extra)
    return SlotReader.smooth_tags(ConfigProcessor.preprocess(conf))


class TestHolidayKeys:
    def test_holiday_name_is_valid(self, holidays):
        assert ConfigProcessor._valid_date_key("thanksgiving", allow_holidays=True)

    def test_holiday_name_starting_with_month(self, holidays):
        assert ConfigProcessor._valid_date_key("May Day", allow_holidays=True)

    def test_unknown_name_rejected(self, holidays):
        with pytest.raises(ConfigurationError, match="custom holiday"):
            ConfigProcessor._valid_date_key("festivus", allow_holidays=True)

    def test_holidays_not_allowed_by_default(self, holidays):
        with pytest.raises(ConfigurationError):
            ConfigProcessor._valid_date_key("thanksgiving")

    def test_week_overrides_reject_holidays(self, holidays):
        conf = {"network_name": "Test", "week_overrides": {"thanksgiving": {}}}
        with pytest.raises(ConfigurationError):
            ConfigProcessor.preprocess(conf)

    def test_override_applies_on_holiday(self, holidays):
        conf = _conf(date_overrides={"thanksgiving": "holiday"})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 11, 26, 8, 0))
        assert slot["tags"] == "parades"
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 11, 19, 20, 0))
        assert slot["tags"] == "sitcoms"


class TestTemplateDateOverrides:
    def test_template_replaces_whole_day(self):
        conf = _conf(date_overrides={"December 25": "holiday"})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 25, 20, 0))
        assert SlotReader.get_tag_from_slot(slot, datetime(2026, 12, 25, 20, 0))[0] is None

    def test_template_does_not_leak_into_other_days(self):
        conf = _conf(date_overrides={"December 25": "holiday"})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 26, 20, 0))
        assert slot["tags"] == "sitcoms"

    def test_range_uses_template(self):
        conf = _conf(date_overrides={"December 24 - January 2": "holiday"})
        slot, _ = SlotReader.get_slot(conf, datetime(2027, 1, 1, 8, 0))
        assert slot["tags"] == "parades"

    def test_inline_override_still_patches(self):
        conf = _conf(date_overrides={"December 25": {"20": {"tags": "movies"}}})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 25, 20, 0))
        assert slot["tags"] == "movies"
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 25, 21, 0))
        assert slot["tags"] == "drama"

    def test_continued_resolves_in_override(self):
        conf = _conf(date_overrides={"December 25": "holiday"})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 25, 9, 0))
        assert slot["tags"] == "parades"

    def test_continued_with_nothing_above_goes_off_air(self):
        conf = _conf(date_overrides={"December 25": {"21": {"continued": True}}})
        slot, _ = SlotReader.get_slot(conf, datetime(2026, 12, 25, 21, 0))
        assert "tags" not in slot


def test_custom_holidays_endpoint(holidays):
    from datetime import date

    from fs42.fs42_server.api.summary import get_custom_holidays

    result = get_custom_holidays()["custom_holidays"]
    year = date.today().year
    assert result["May Day"] == {"rule": "May 1", "date": f"{year}-05-01"}
    thanksgiving = date.fromisoformat(result["thanksgiving"]["date"])
    assert thanksgiving.month == 11 and thanksgiving.weekday() == 3 and 22 <= thanksgiving.day <= 28


def test_station_manager_reload_rereads_holidays(holidays):
    from unittest.mock import patch

    from fs42.station_manager import StationManager
    from fs42.station_io import StationIO

    config_data = {"server_port": 4242, "custom_holidays": {"thanksgiving": "4th thursday november"}}
    with patch.object(StationIO, "load_main_config", return_value=config_data):
        with patch("fs42.station_io.glob.glob", return_value=[]):
            StationManager().reload()

    assert StationManager().get_custom_holidays() == {"thanksgiving": "4th thursday november"}
    assert ConfigProcessor._valid_date_key("thanksgiving", allow_holidays=True)
    with pytest.raises(ConfigurationError):
        ConfigProcessor._valid_date_key("May Day", allow_holidays=True)
