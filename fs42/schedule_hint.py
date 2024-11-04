
from datetime import datetime
from fs42.timings import MONTHS
import re

#all hints should implement this interface
class TemporalHint:

    def __init__(self):
        pass

    @staticmethod
    def test_pattern(to_test):
        pass

    #when is a datetime object for the time slot
    def hint(self, when):
        return True

class MonthHint:

    def __init__(self, month_name):
        self.month_name = month_name
        self.month_number = datetime.strptime(self.month_name, "%B").month

    @staticmethod
    def test_pattern(to_test):
        return to_test in MONTHS

    #when should be a datetime object
    def hint(self, when):
        return when.month == self.month_number


class QuarterHint:

    quarter_patten = re.compile("^[q|Q][1-4]$")

    def __init__(self, quarter_name):
        self.quarter_name = quarter_name.lower()
        self.quarter = 0
        if QuarterHint.test_pattern(quarter_name):
            self.quarter = int(self.quarter_name.strip("Qq"))
        else:
            raise ValueError("Quarter name not valid: {quarter_name}- should be one of Q1-Q4 or q1-q4")

    def test_pattern(to_test):
        m = QuarterHint.quarter_patten.match(to_test)
        if m is None:
            return False
        return True

    #when should be a datetime object
    def hint(self, when):
        return (int(when.month/3) + 1) == self.quarter



