import calendar
import datetime
MONTHS = list(calendar.month_name)[1:]
OPERATING_HOURS = [6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,0,1,2,3,4,5]
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
HOUR2 = 7200
HOUR = 3600
H_HOUR = 1800
Q_HOUR = 900
MIN_10 = 600
MIN_5 = 300
MIN_3 = 180
MIN_2 = 120
MIN_1 = 60



def next_week(when):
    weekday = when.weekday()
    print(weekday)
    #go one day past the EOW (weekday is 0-6)
    eow = when + datetime.timedelta( days=(7-weekday))
    return datetime.datetime(eow.year, eow.month, eow.day)

def next_month(when):
    eom = (when.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    return datetime.datetime(eom.year, eom.month, eom.day)