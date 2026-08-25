from unittest.mock import patch
from datetime import datetime

from fs42 import schedule_hint
from fs42.media_processor import MediaProcessor
from fs42.station_io import StationIO
from fs42.station_manager import StationManager


class TestFolderHints:
    def setup_method(self):
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        config_data = {
            "server_port": 4242,
            "custom_holidays": {"aug_day": "August 29", "thanksgiving": "4th thursday november"},
        }
        with patch.object(StationIO, "load_main_config", return_value=config_data):
            with patch("fs42.station_io.glob.glob", return_value=[]):
                StationManager()

    def _hints_for(self, folder, bumpdir=False):
        hints = MediaProcessor._process_hints(f"catalog/test/{folder}", "tag", bumpdir=bumpdir)
        return sorted(type(hint).__name__ for hint in hints)

    def test_existing_folder_names_still_match(self):
        assert self._hints_for("October") == ["MonthHint"]
        assert self._hints_for("Q4") == ["QuarterHint"]
        assert self._hints_for("December 1 - December 25") == ["RangeHint"]
        assert self._hints_for("morning") == ["DayPartHint"]
        assert self._hints_for("friday") == ["DayofWeekHint"]

    def test_unhinted_folder_gets_nothing(self):
        assert self._hints_for("cartoons") == []

    def test_bump_hint_only_applies_to_bump_dirs(self):
        assert self._hints_for("pre") == []
        assert self._hints_for("pre", bumpdir=True) == ["BumpHint"]

    def test_week_number_folder(self):
        assert self._hints_for("week number 44") == ["WeekNumberHint"]
        # a bare number is not a week number - test_pattern stays strict
        assert self._hints_for("44") == []

    def test_custom_holiday_folder(self):
        assert self._hints_for("aug_day") == ["CustomHolidayHint"]
        assert self._hints_for("thanksgiving") == ["CustomHolidayHint"]

    def test_custom_holiday_folder_is_case_sensitive(self):
        # holiday names are matched against the config keys exactly
        assert self._hints_for("Aug_Day") == []

    def test_holiday_folder_restricts_by_date(self):
        (hint,) = MediaProcessor._process_hints("catalog/test/aug_day", "tag")
        assert hint.hint(datetime(2026, 8, 29, 12))
        assert not hint.hint(datetime(2026, 8, 28, 12))

    def test_matching_folder_names_stack(self):
        # every pattern that matches is applied, and _test_candidate_hints
        # requires all of them to pass
        StationManager().server_conf["custom_holidays"]["October"] = "October 5"
        assert self._hints_for("October") == ["CustomHolidayHint", "MonthHint"]


class TestHintJSONRoundTrip:
    def setup_method(self):
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        config_data = {"server_port": 4242, "custom_holidays": {"aug_day": "August 29"}}
        with patch.object(StationIO, "load_main_config", return_value=config_data):
            with patch("fs42.station_io.glob.glob", return_value=[]):
                StationManager()

    def test_every_registered_type_round_trips(self):
        originals = [
            schedule_hint.MonthHint("October"),
            schedule_hint.QuarterHint("Q4"),
            schedule_hint.RangeHint("December 1 - December 25"),
            schedule_hint.DayPartHint("morning"),
            schedule_hint.DayofWeekHint("friday"),
            schedule_hint.BumpHint("pre"),
            schedule_hint.WeekNumberHint("week number 44"),
            schedule_hint.CustomHolidayHint("aug_day"),
        ]
        assert len(originals) == len(schedule_hint.HINT_KLASS_BY_TYPE)

        for original in originals:
            as_json = original.toJSON()
            klass = schedule_hint.HINT_KLASS_BY_TYPE[as_json["type"]]
            rebuilt = klass.fromJSON(as_json)
            assert type(rebuilt) is type(original)
            assert rebuilt.toJSON() == as_json

    def test_round_trip_preserves_matching(self):
        when_hits = datetime(2026, 8, 29, 12)
        when_misses = datetime(2026, 8, 28, 12)
        original = schedule_hint.CustomHolidayHint("aug_day")
        rebuilt = schedule_hint.CustomHolidayHint.fromJSON(original.toJSON())
        assert rebuilt.hint(when_hits)
        assert not rebuilt.hint(when_misses)

    def test_unknown_type_is_skipped_not_fatal(self):
        assert schedule_hint.HINT_KLASS_BY_TYPE.get("not_a_real_type") is None