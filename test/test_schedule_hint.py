import unittest
from datetime import datetime
from fs42.timings import MONTHS
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint

class TestMonthHint(unittest.TestCase):

    def test_hint(self):
        hint = MonthHint("November")
        when = datetime.fromisoformat('1972-11-17')
        self.assertTrue(hint.hint(when))


    def test_wrong_hint(self):
        hint = MonthHint("December")
        when = datetime.fromisoformat('1972-11-17')
        self.assertFalse(hint.hint(when))

    def test_all_months(self):
        count = 1
        for month in MONTHS:
            hint = MonthHint(month)
            when = datetime.strptime(month, "%B")
            self.assertTrue(hint.hint(when))
            count += 1

    def test_test_pattern(self):
        self.assertFalse(MonthHint.test_pattern("aaaa"))
        self.assertTrue(MonthHint.test_pattern("July"))
        self.assertTrue(MonthHint.test_pattern("November"))

class TestQuarterHint(unittest.TestCase):

    def test_quarter(self):
        hint = QuarterHint("Q1")
        when = datetime.fromisoformat('2001-02-17')
        self.assertTrue(hint.hint(when))

    def test_wrong_quarters(self):
        hint = QuarterHint("Q4")
        when = datetime.fromisoformat('2011-05-13')
        self.assertFalse(hint.hint(when))

    def test_wrong_parameter(self):
        with self.assertRaises(ValueError):
            hint = QuarterHint("Q5")
        with self.assertRaises(ValueError):
            hint = QuarterHint("p3")

    def test_test_pattern(self):
        self.assertFalse(QuarterHint.test_pattern("sq1d"))
        self.assertFalse(QuarterHint.test_pattern("q2sd"))
        self.assertFalse(QuarterHint.test_pattern("s2q3"))
        self.assertTrue(QuarterHint.test_pattern("q1"))
        self.assertTrue(QuarterHint.test_pattern("q3"))


class TestRangeHint(unittest.TestCase):

    def test_range(self):
        hint = RangeHint("December 1 - December 25")
        #self.assertTrue(hint.hint(datetime.fromisoformat('2024-12-15')))
        #self.assertFalse(hint.hint(datetime.fromisoformat('2024-01-15')))


    def test_range_cross_year(self):
        hint = RangeHint("December 1 - January 31")
        self.assertTrue(hint.hint(datetime.fromisoformat('2024-12-15')))
        self.assertTrue(hint.hint(datetime.fromisoformat('2025-01-10')))
        self.assertTrue(hint.hint(datetime.fromisoformat('2024-01-10')))
        self.assertTrue(hint.hint(datetime.fromisoformat('1985-01-10')))
        self.assertFalse(hint.hint(datetime.fromisoformat('2025-04-15')))
        self.assertFalse(hint.hint(datetime.fromisoformat('2040-04-15')))
        self.assertFalse(hint.hint(datetime.fromisoformat('1976-04-15')))

    def test_test_pattern(self):
        self.assertTrue(RangeHint.test_pattern("December 1 - December 25"))
        self.assertTrue(RangeHint.test_pattern("November  11 - December  15"))
        self.assertTrue(RangeHint.test_pattern(" June    1 - JULY 25    "))
        self.assertTrue(RangeHint.test_pattern("april 13 -  august 16"))
        self.assertTrue(RangeHint.test_pattern("march 3   april 07"))
        self.assertFalse(RangeHint.test_pattern("October 42 - December 13"))
        self.assertFalse(RangeHint.test_pattern("December 32 - December 13"))
        self.assertFalse(RangeHint.test_pattern("ExtraStuff December 1 - December 25"))
        self.assertFalse(RangeHint.test_pattern("December 1 - December 25 and this stuff"))

