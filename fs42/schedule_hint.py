from datetime import datetime, timedelta
import re

from fs42 import timings
from fs42 import station_manager

# all temporal hints should implement this interface
class TemporalHint:
    def __init__(self):
        pass

    @staticmethod
    def test_pattern(to_test):
        pass

    # when is a datetime object for the time slot
    def hint(self, when):
        return True

class DayofWeekHint:
    def __init__(self, day_name):
        self.day_name = day_name
        self.type = "day_of_week"

    @staticmethod
    def test_pattern(to_test):
        return to_test in timings.DAYS

    def hint(self, when):
        return  when.strftime("%A").lower() == self.day_name

    
    def toJSON(self):
        return {"type": self.type, "day": self.day_name}

    def fromJSON(json_data):
        return MonthHint(json_data["day"])
    
class DayPartHint:
    def __init__(self, part_name):
        self.part_name = part_name
        self.type = "day_part"

    @staticmethod
    def test_pattern(to_test):
        return to_test in station_manager.StationManager().get_day_parts().keys()

    def hint(self, when):
        return when.hour in station_manager.StationManager().get_day_parts()[self.part_name]

    def __str__(self):
        return f"{self.part_name}"

    def toJSON(self):
        return {"type": self.type, "part": self.part_name}

    def fromJSON(json_data):
        return DayPartHint(json_data["part"])


class BumpHint:
    pre = "pre"
    post = "post"

    def __init__(self, where="pre"):
        self.where = where
        self.type = "bump"

    @staticmethod
    def test_pattern(to_test):
        return to_test == BumpHint.pre or to_test == BumpHint.post

    def hint(self, when):
        # always return true, since it doesn't really matter when
        return True

    def __str__(self):
        return f"bump:{self.where}"

    def toJSON(self):
        return {"type": self.type, "where": self.where}

    def fromJSON(json_data):
        return BumpHint(json_data["where"])

class WeekNumberHint:
    pattern = re.compile("^week number ([1-9]|[1-4][0-9]|5[0-3])$", re.IGNORECASE)

    def __init__(self, week_name):
        self.week_name = week_name
        self.week_number = datetime
        if WeekNumberHint.test_pattern(week_name):
            self.week_number = int(self.week_name.lower().strip("week number"))
        else:
            raise ValueError(f"Week Number not valid: {week_name}- Sholud be 'week number <1-53>'")
        self.type = "week_number"

    @staticmethod
    def test_pattern(to_test):
        m = WeekNumberHint.pattern.match(to_test)
        a = False if m is None else True
        return a

    # when should be a datetime object
    def hint(self, when):
        return when.isocalendar().week == self.week_number

    def toJSON(self):
        return {"type": self.type, "week_number": self.week_name}

    def fromJSON(json_data):
        return WeekNumberHint(json_data["week_number"])

class MonthHint:
    def __init__(self, month_name):
        self.month_name = month_name
        self.month_number = datetime.strptime(self.month_name, "%B").month
        self.type = "month"

    @staticmethod
    def test_pattern(to_test):
        return to_test in timings.MONTHS

    # when should be a datetime object
    def hint(self, when):
        return when.month == self.month_number

    def __str__(self):
        return self.month_name

    def toJSON(self):
        return {"type": self.type, "month": self.month_name}

    def fromJSON(json_data):
        return MonthHint(json_data["month"])


class QuarterHint:
    pattern = re.compile("^[q|Q][1-4]$")

    def __init__(self, quarter_name):
        self.quarter_name = quarter_name.lower()
        self.quarter = 0
        if QuarterHint.test_pattern(quarter_name):
            self.quarter = int(self.quarter_name.strip("Qq"))
        else:
            # this should be a runtime error
            raise ValueError("Quarter name not valid: {quarter_name}- should be one of Q1-Q4 or q1-q4")
        self.type = "quarter"

    @staticmethod
    def test_pattern(to_test):
        m = QuarterHint.pattern.match(to_test)
        a = False if m is None else True
        return a

    # when should be a datetime object
    def hint(self, when):
        return (when.month - 1) // 3 + 1 == self.quarter

    def __str__(self):
        return self.quarter_name

    def toJSON(self):
        return {"type": self.type, "quarter": self.quarter_name}

    def fromJSON(json_data):
        return QuarterHint(json_data["quarter"])

class CustomHolidayHint:
    fixed_pattern = re.compile(f"^ *({'|'.join(timings.MONTHS)}) *([0-3]?[0-9])$", re.IGNORECASE)
    ordinal_pattern = re.compile(f"^(1st|2nd|3rd|4th|last) ({'|'.join(timings.DAYS)}) ({'|'.join(timings.MONTHS)})$", re.IGNORECASE)

    def __init__(self, holiday_name):
        self.holiday_name = holiday_name

        # grab config from the station_manager
        if CustomHolidayHint.test_pattern(holiday_name):
            holiday_conf_str = station_manager.StationManager().get_custom_holidays().get(holiday_name)
        else:
            raise ValueError(f"Custom Holiday: {holiday_name} not found in main config")
        
        fixed_m = CustomHolidayHint.fixed_pattern.match(holiday_conf_str)
        ordinal_m = CustomHolidayHint.ordinal_pattern.match(holiday_conf_str)

        self.month = None
        self.day = None
        self.weekday_str = None
        self.n = None

        if fixed_m:
            self.month = fixed_m.group(1).capitalize()
            self.day = int(fixed_m.group(2))
        elif ordinal_m:
            self.month = ordinal_m.group(3).capitalize()
            self.weekday_str = ordinal_m.group(2).lower()
            self.n = -1 if not ordinal_m.group(1)[0].isdigit() else int(ordinal_m.group(1)[0])

        else:
            raise ValueError(f"Custom Holiday: {holiday_name} date string not valid.")

        self.type = "custom_holiday"

    @staticmethod        
    def test_pattern(to_test):
        return to_test in station_manager.StationManager().get_custom_holidays().keys()

    def hint(self, when):
        year = when.year
        if self.day:
            raw_date = datetime.strptime(f"{year} {self.month} {self.day}", "%Y %B %d")
            calc_date = self._find_weekday(raw_date)
        elif self.weekday_str:
            raw_date = datetime.strptime(f"{year} {self.month} 1", "%Y %B %d")
            calc_date = self._nth_weekday(raw_date, self.weekday_str, self.n)
        else:
            # left for expansion
            # raise error in case we find ourselves here
            raise ValueError(f"Custom Holiday: {self.holiday_name} configuration read error.")

        return calc_date.day == when.day and calc_date.month == when.month
    
    def _find_weekday(self, raw_date):
        # finds the nearest weekday
        if raw_date.weekday() == 5:
            return raw_date - timedelta(days=1)
        elif raw_date.weekday() == 6:
            return raw_date + timedelta(days=1)
        return raw_date
    
    def _nth_weekday(self, month, weekday_str, n):
        # Assumes month is a datetime set to the 1st of the month.
        # Find the offset from the first
        weekday = timings.DAYS.index(weekday_str.lower())
        offset = (weekday - month.weekday()) % 7
        last_day = self._find_last_day(month)
        if n >= 0:
            day = 1 + offset + (n-1) * 7
            return month.replace(day=day)
        else:
            return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


    def _find_last_day(self, when):
        if when.month == 12:
            next_first = when.replace(year=when.year+1, month=1, day=1)
        else:
            next_first = when.replace(month=when.month+1, day=1)
        return next_first - timedelta(days=1) 

    def toJSON(self):
        return {"type": self.type, "custom_holiday": self.holiday_name}

    def fromJSON(json_data):
        return CustomHolidayHint(json_data["custom_holiday"])


class RangeHint:
    # matches patterns like: December 1 - December 25
    pattern = re.compile(
        f"^ *({'|'.join(timings.MONTHS)}) *([0-3]?[0-9]) *-? *({'|'.join(timings.MONTHS)}) *([0-3]?[0-9]) *$",
        re.IGNORECASE,
    )

    def __init__(self, range_string):
        self.start_date = None
        self.end_date = None
        self.range_string = range_string
        if RangeHint.test_pattern(range_string):
            m = RangeHint.pattern.match(range_string)
            try:
                (self.start_date, self.end_date) = RangeHint._scrape_dates(m)

            except ValueError:
                # this should be a runtime error
                raise ValueError("Date range not valid - should be of form: December 1 - December 25")
        self.type = "range"

    @staticmethod
    def _scrape_dates(m):
        # this WILL throw a value error if not valid date ranges
        start = datetime.strptime(f"{m.group(1).capitalize()} {m.group(2):0>2}", "%B %d")
        end = datetime.strptime(f"{m.group(3).capitalize()} {m.group(4):0>2}", "%B %d")
        return (start, end)

    @staticmethod
    def test_pattern(to_test):
        m = RangeHint.pattern.match(to_test)
        a = False if m is None else True
        if a:
            # check that it can be a valid date
            try:
                (start, end) = RangeHint._scrape_dates(m)
            except ValueError:
                a = False
        return a

    def hint(self, when):
        # lets put stuff in the current years context first

        test_start = self.start_date
        test_end = self.end_date

        # this will only consider month and day, since the years are the same
        if self.start_date > self.end_date:
            # Crosses year boundary: something like Nov 15 - Jan 15
            if test_start.replace(year=when.year) <= when:
                # scenario 1: we are past the start date, like Nov 20
                test_start = test_start.replace(year=when.year)
                test_end = test_end.replace(year=when.year + 1)
            else:
                # scenario 2: we are before the start date - like Jan 15
                test_start = test_start.replace(year=when.year - 1)
                test_end = test_end.replace(year=when.year)
        else:
            # the simple case - they are both in the current year

            test_start = test_start.replace(year=when.year)
            test_end = test_end.replace(year=when.year)

        if test_start <= when and test_end >= when:
            return True
        else:
            return False

    def __str__(self):
        return "range_hint"

    def toJSON(self):
        return {
            "type": self.type,
            "range_string": self.range_string,
        }

    def fromJSON(json_data):
        return RangeHint(f"{json_data['range_string']}")


def hint_klass_matcher(to_test: str):
    klasses = [MonthHint, QuarterHint, RangeHint, DayofWeekHint, WeekNumberHint, CustomHolidayHint]
    for klass in klasses:
        if klass.test_pattern(to_test):
            return klass
    return None
