from unittest.mock import patch
from datetime import datetime
from fs42.timings import MONTHS
from fs42.station_manager import StationManager
from fs42.station_io import StationIO
from fs42.schedule_hint import WeekNumberHint, MonthHint, QuarterHint, CustomHolidayHint, RangeHint
import pytest

class TestWeekNumberHint:
    def test_hint_week_1(self):
        hint = WeekNumberHint('week number 1')
        assert hint.hint(datetime.fromisoformat('2025-12-29'))
        assert not hint.hint(datetime.fromisoformat('2027-01-02'))

    def test_hint_week_53(self):
        hint = WeekNumberHint('week number 53')
        assert hint.hint(datetime.fromisoformat('2026-12-29'))
        assert not hint.hint(datetime.fromisoformat('2026-12-27'))

    def test_wrong_hint(self):
        hint = WeekNumberHint('week number 2')
        assert not hint.hint(datetime.fromisoformat('2026-03-18'))

    def test_test_pattern(self):
        assert WeekNumberHint.test_pattern('week number 2')
        assert WeekNumberHint.test_pattern('Week Number 5')
        assert not WeekNumberHint.test_pattern('week number 54')
        assert not WeekNumberHint.test_pattern('aaaaa')
        assert not WeekNumberHint.test_pattern('week number -10')

class TestMonthHint:
    def test_hint(self):
        hint = MonthHint("November")
        when = datetime.fromisoformat('1972-11-17')
        assert hint.hint(when)

    def test_wrong_hint(self):
        hint = MonthHint("December")
        when = datetime.fromisoformat('1972-11-17')
        assert not hint.hint(when)

    def test_all_months(self):
        for month in MONTHS:
            hint = MonthHint(month)
            when = datetime.strptime(month, "%B")
            assert hint.hint(when)

    def test_test_pattern(self):
        assert not MonthHint.test_pattern("aaaa")
        assert MonthHint.test_pattern("July")
        assert MonthHint.test_pattern("November")

class TestQuarterHint:
    def test_quarter(self):
        hint = QuarterHint("Q1")
        when = datetime.fromisoformat('2001-02-17')
        assert hint.hint(when)

    def test_wrong_quarters(self):
        hint = QuarterHint("Q4")
        when = datetime.fromisoformat('2011-05-13')
        assert not hint.hint(when)

    def test_wrong_parameter(self):
        with pytest.raises(ValueError):
            QuarterHint("Q5")
        with pytest.raises(ValueError):
            QuarterHint("p3")

    def test_test_pattern(self):
        assert not QuarterHint.test_pattern("sq1d")
        assert not QuarterHint.test_pattern("q2sd")
        assert not QuarterHint.test_pattern("s2q3")
        assert QuarterHint.test_pattern("q1")
        assert QuarterHint.test_pattern("q3")

class TestCustomHolidayHint:
    def setup_method(self):
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

    def _make_manager(self, custom_holidays):
        config_data = {"server_port": 4242, "custom_holidays": custom_holidays}
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.station_io.glob.glob', return_value=[]):
                return StationManager()

    def test_fixed_date_is_literal(self):
        self._make_manager({"christmas": "December 25"})
        hint = CustomHolidayHint("christmas")
        # Dec 25, 2025 is a Thursday
        assert hint.hint(datetime.fromisoformat('2025-12-25'))
        assert not hint.hint(datetime.fromisoformat('2025-12-24'))
        # Dec 25, 2027 is a Saturday - still the 25th, no shifting to the 24th
        assert hint.hint(datetime.fromisoformat('2027-12-25'))
        assert not hint.hint(datetime.fromisoformat('2027-12-24'))
        # Dec 25, 2021 is a Sunday - still the 25th, no shifting to the 26th
        assert hint.hint(datetime.fromisoformat('2021-12-25'))
        assert not hint.hint(datetime.fromisoformat('2021-12-26'))

    def test_fixed_date_across_year_boundary(self):
        # the old weekend shift could push a date into an adjacent year, where the
        # month/day comparison then matched nothing at all
        self._make_manager({"newyears": "January 1"})
        hint = CustomHolidayHint("newyears")
        # Jan 1, 2028 is a Saturday
        assert hint.hint(datetime.fromisoformat('2028-01-01'))
        assert not hint.hint(datetime.fromisoformat('2027-12-31'))

    def test_ordinal_holiday(self):
        self._make_manager({"thanksgiving": "4th thursday november"})
        hint = CustomHolidayHint("thanksgiving")
        assert hint.hint(datetime.fromisoformat('2026-11-26'))
        assert not hint.hint(datetime.fromisoformat('2026-11-25'))

    def test_ordinal_uppercase(self):
        self._make_manager({"thanksgiving": "4th Thursday November"})
        hint = CustomHolidayHint("thanksgiving")
        assert hint.hint(datetime.fromisoformat('2026-11-26'))
        assert not hint.hint(datetime.fromisoformat('2026-11-25'))

    def test_last_weekday(self):
        self._make_manager({"memorial_day": "last monday may"})
        hint = CustomHolidayHint("memorial_day")
        assert hint.hint(datetime.fromisoformat('2026-05-25'))
        assert not hint.hint(datetime.fromisoformat('2026-05-26'))

    def test_test_pattern(self):
        self._make_manager({"memorial_day": "last monday may"})
        assert not CustomHolidayHint.test_pattern('around memorial day')
        assert not CustomHolidayHint.test_pattern('MeMoRiAl_DaY')
        assert CustomHolidayHint.test_pattern('memorial_day')

class TestRangeHint:
    def test_range(self):
        hint = RangeHint("December 1 - December 25")
        assert hint.hint(datetime.fromisoformat('2024-12-15'))
        assert not hint.hint(datetime.fromisoformat('2024-01-15'))

    def test_range_cross_year(self):
        hint = RangeHint("December 1 - January 31")
        assert hint.hint(datetime.fromisoformat('2024-12-15'))
        assert hint.hint(datetime.fromisoformat('2025-01-10'))
        assert hint.hint(datetime.fromisoformat('2024-01-10'))
        assert hint.hint(datetime.fromisoformat('1985-01-10'))
        assert not hint.hint(datetime.fromisoformat('2025-04-15'))
        assert not hint.hint(datetime.fromisoformat('2040-04-15'))
        assert not hint.hint(datetime.fromisoformat('1976-04-15'))

    def test_test_pattern(self):
        assert RangeHint.test_pattern("December 1 - December 25")
        assert RangeHint.test_pattern("November  11 - December  15")
        assert RangeHint.test_pattern(" June    1 - JULY 25    ")
        assert RangeHint.test_pattern("april 13 -  august 16")
        assert RangeHint.test_pattern("march 3   april 07")
        assert not RangeHint.test_pattern("October 42 - December 13")
        assert not RangeHint.test_pattern("December 32 - December 13")
        assert not RangeHint.test_pattern("ExtraStuff December 1 - December 25")
        assert not RangeHint.test_pattern("December 1 - December 25 and this stuff")
