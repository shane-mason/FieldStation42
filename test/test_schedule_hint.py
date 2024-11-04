import unittest
from datetime import datetime
from fs42.timings import MONTHS
from fs42.schedule_hint import MonthHint, QuarterHint

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

if __name__ == '__main__':
    unittest.main()
