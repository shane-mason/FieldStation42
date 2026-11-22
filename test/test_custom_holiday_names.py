from unittest.mock import patch

import pytest

# station_manager has to be imported before station_io. fs42.station_io imports
# schedule_hint, which imports station_manager, which imports StationIO back - so
# reaching station_io first hits its class body before it has run.
from fs42.station_manager import StationManager, StationConfigError
from fs42.station_io import StationIO


def _load(custom_holidays, day_parts=None):
    # reset the Borg singleton so each call starts clean
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    config_data = {"server_port": 4242, "custom_holidays": custom_holidays}
    if day_parts:
        config_data["day_parts"] = day_parts
    with patch.object(StationIO, "load_main_config", return_value=config_data):
        with patch("fs42.station_io.glob.glob", return_value=[]):
            return StationManager()


class TestCustomHolidayNameValidation:
    # a holiday name is matched as a bare string against folder names and marathon
    # hints, so one that also reads as a built-in hint fails quietly at runtime

    def test_ordinary_names_are_accepted(self):
        manager = _load({
            "thanksgiving": "4th thursday november",
            "aug_day": "August 29",
            "station_anniversary": "September 30",
        })
        assert len(manager.get_custom_holidays()) == 3

    @pytest.mark.parametrize("name,collides_with", [
        ("October", "MonthHint"),
        ("Q4", "QuarterHint"),
        ("friday", "DayofWeekHint"),
        ("morning", "DayPartHint"),
        ("week number 20", "WeekNumberHint"),
        ("December 1 - December 25", "RangeHint"),
        ("pre", "BumpHint"),
    ])
    def test_names_that_collide_are_rejected(self, name, collides_with):
        # load_main_config wraps config failures in StationConfigError
        with pytest.raises(StationConfigError) as err:
            _load({name: "August 29"})
        message = str(err.value)
        assert name in message
        assert collides_with in message

    def test_collision_with_a_custom_day_part_is_caught(self):
        day_parts = {"insomnia": {"start_hour": 2, "end_hour": 5}}
        with pytest.raises(StationConfigError, match="DayPartHint"):
            _load({"insomnia": "August 29"}, day_parts=day_parts)

    def test_a_name_is_not_treated_as_colliding_with_itself(self):
        manager = _load({"aug_day": "August 29"})
        assert "aug_day" in manager.get_custom_holidays()

    def test_no_custom_holidays_is_fine(self):
        manager = _load({})
        assert manager.get_custom_holidays() == {}