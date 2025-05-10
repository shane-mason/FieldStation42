from datetime import datetime
from fs42.timings import MONTHS
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint
import pytest

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
