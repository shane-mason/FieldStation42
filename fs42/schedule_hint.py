
from datetime import datetime
import re
import copy

from fs42 import timings


class TagHintReader():

    @staticmethod
    def start_of_week(when_date):
        #return date.replace()
        pass

    @staticmethod
    def get_tag(conf, when:datetime):
        day_str = timings.DAYS[when.weekday()]
        slot_number = str(when.hour)
        response = None
        if day_str in conf:
            if slot_number in conf[day_str]:
                if 'tags' in conf[day_str][slot_number]:
                    slot = conf[day_str][slot_number]['tags']
                    
                    if type(slot) is list:
                        if len(slot) == 1 or when.minute < 30:
                            return slot[0]
                        else:
                            return slot[1]
                    else:
                        return conf[day_str][slot_number]['tags']
                
        return response
    
    @staticmethod
    def smooth_tags(conf):
        last_tag = None
        smoothed = copy.deepcopy(conf)
        for day_index in timings.DAYS:
            for slot_index in timings.OPERATING_HOURS:
                slot_index = str(slot_index)
                if slot_index in conf[day_index]:
                    if 'tags' in conf[day_index][slot_index]:
                        last_tag = conf[day_index][slot_index]
                    elif 'continued' in conf[day_index][slot_index]:
                        if conf[day_index][slot_index]['continued'] == True:
                            smoothed[day_index][slot_index]['tags'] = last_tag['tags']
        return smoothed


    @staticmethod
    def complete_state(conf):
        onair_state = None
        completed = copy.deepcopy
        for day_index in timings.DAYS:
            for slot_index in timings.OPERATING_HOURS:
                #did we transition? if so, mark it
                if slot_index in conf[day_index]:
                    #then onair
                    pass
                else:
                    #then offair
                    pass

#all temporal hints should implement this interface
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
        return to_test in timings.MONTHS

    #when should be a datetime object
    def hint(self, when):
        return when.month == self.month_number
    
    def __str__(self):
        return self.month_name


class QuarterHint:

    pattern = re.compile("^[q|Q][1-4]$")

    def __init__(self, quarter_name):
        self.quarter_name = quarter_name.lower()
        self.quarter = 0
        if QuarterHint.test_pattern(quarter_name):
            self.quarter = int(self.quarter_name.strip("Qq"))
        else:
            #this should be a runtime error
            raise ValueError("Quarter name not valid: {quarter_name}- should be one of Q1-Q4 or q1-q4")

    @staticmethod
    def test_pattern(to_test):
        m = QuarterHint.pattern.match(to_test)
        a = False if m is None else True
        return a

    #when should be a datetime object
    def hint(self, when):
        return (int(when.month/3) + 1) == self.quarter

    def __str__(self):
        return self.quarter_name

class RangeHint:

    #matches patterns like: December 1 - December 25
    pattern = re.compile(f"^ *({'|'.join(timings.MONTHS)}) *([0-3]?[0-9]) *-? *({'|'.join(timings.MONTHS)}) *([0-3]?[0-9]) *$", re.IGNORECASE)

    def __init__(self, range_string):
        self.start_date = None
        self.end_date = None
        if RangeHint.test_pattern(range_string):
            m = RangeHint.pattern.match(range_string)
            try:
                (self.start_date, self.end_date) = RangeHint._scrape_dates(m)

            except ValueError:
                #this should be a runtime error
                raise ValueError("Date range not valid - should be of form: December 1 - December 25")



    @staticmethod
    def _scrape_dates(m):
        #this WILL throw a value error if not valid date ranges
        start = datetime.strptime(f"{m.group(1).capitalize()} {m.group(2):0>2}", "%B %d")
        end = datetime.strptime(f"{m.group(3).capitalize()} {m.group(4):0>2}", "%B %d")
        return (start, end)

    @staticmethod
    def test_pattern(to_test):
        m = RangeHint.pattern.match(to_test)
        a = False if m is None else True
        if a:
            #check that it can be a valid date
            try:
                (start, end) = RangeHint._scrape_dates(m)
            except ValueError:
                a = False
        return a


    def hint(self, when):
        #lets put stuff in the current years context first

        test_start = self.start_date
        test_end = self.end_date

        #this will only consider month and day, since the years are the same
        if self.start_date > self.end_date:

            #Crosses year boundary: something like Nov 15 - Jan 15
            if( test_start.replace(year=when.year) <= when):
                #scenario 1: we are past the start date, like Nov 20
                test_start = test_start.replace(year=when.year)
                test_end = test_end.replace(year=when.year+1)
            else:
                #scenario 2: we are before the start date - like Jan 15
                test_start = test_start.replace(year=when.year-1)
                test_end = test_end.replace(year=when.year)
        else:
            #the simple case - they are both in the current year

            test_start = test_start.replace(year=when.year)
            test_end = test_end.replace(year=when.year)

        if test_start <= when and test_end >= when:
            return True
        else:
            return False

    def __str__(self):
        return f"range_hint"