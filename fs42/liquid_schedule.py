import os
import sys
sys.path.append(os.getcwd())
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)

import datetime
import calendar
import copy

from fs42.catalog import ShowCatalog
from fs42.station_manager import StationManager
from fs42.schedule_hint import TagHintReader
from fs42 import timings


    
class LiquidBlock():

    def __init__(self, content, start_time, end_time):
        self.content = content
        #the requested starting time
        self.start_time = start_time
        #the expected/requested end time
        self.end_time = end_time

    def content_duration(self):
        return self.content.duration
    
    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    def make_plan(self, catalog:ShowCatalog):
        diff = self.playback_duration() - self.content_duration()
        if diff < 0:
            raise(ValueError("Schedule logic error: duration is greater than content"))
        if diff > 0: 
            reel_blocks = catalog.make_reel_fill(self.start_time, diff)
            print(reel_blocks)




class LiquidClipBlock(LiquidBlock):

    def __init__(self, content, start_time, end_time):
        if type(content) is list:
            super().__init__(content, start_time, end_time)
        else:
            raise(TypeError(f"LiquidClipBlock required content of type list. Got {type(content)} instead"))
        
    def content_duration(self):
        dur = 0
        for clip in self.content:
            dur += clip.duration
        return dur

    
class LiquidSchedule():

    def __init__(self, conf):
        self._l = logging.getLogger("Liquid")
        self.conf = TagHintReader.smooth_tags(conf)
        self.catalog = ShowCatalog(conf)
        self._blocks = self._load_blocks()
        
    def _calc_duration(self, content_runtime):
        if self.conf['network_type'] == "flow":
            return content_runtime
        
        #  

    def _load_blocks(self):
        return []

    def _end_time(self):
        if len(self._blocks) > 0:
            return self._blocks[-1].end_time
        else:
            return None
        
    def rebuild_schedule(self, start_time=None, end_time=None):
        self._blocks = []
        self.build_month()

    def build_month(self):
        for_month = datetime.date.today()
        (weekday, days_in_month) = calendar.monthrange(for_month.year, for_month.month)
        for i in range(1, days_in_month):
            target_date = for_month.replace(day=i)
            self.add_day(target_date)

    def add_day(self, target_date):
        for hour in timings.OPERATING_HOURS:
            tag = TagHintReader.get_tag(self.conf, target_date.weekday(), hour)
            print(f"Day={target_date.weekday()} Slot={hour} Tag={tag}")
            if tag is not None:
                candidate = self.catalog.find_candidate(tag, timings.HOUR*23, target_date)
                print(candidate)
            else:
                #make offair
                pass 

    def add_fluid(self, end_target):
        current_mark = self._end_time()
        if current_mark is None:
            current_mark = datetime.datetime.now()

        while current_mark < end_target:
            print(f"Current mark: {current_mark} {current_mark.weekday()} {current_mark.hour}")
            tag = TagHintReader.get_tag(self.conf, current_mark.weekday(), current_mark.hour)
            if tag is not None:
                candidate = self.catalog.find_candidate(tag, timings.HOUR*23, current_mark)
                if candidate is None:
                    #this should only happen on an error (have a tag, but no candidate)
                    self._l.error(f"Could not find content for tag {tag} - please add content, chech your configuration and retry")
                    sys.exit(-1)
            else:
                #then we are offair - get offair video
                candidate = self.catalog.get_offair()
                if candidate is None:
                    self._l.error(f"Schedule logic error: no schedule hints for {current_mark}")
                    self._l.error("This indicates that the station is offair, but offair content is not configured")
                    self._l.error(f"Configure 'off_air_video' or 'off_air_image' for {self.conf['network_name']}")
                    sys.exit(-1)
                

            next_mark = current_mark + datetime.timedelta(seconds=candidate.duration)
            self._blocks.append(LiquidBlock(candidate, current_mark, next_mark))
            current_mark = next_mark



#print(calendar.monthrange(2024, 12))
conf = StationManager().station_by_name("indie42")
liq = LiquidSchedule(conf)
liq.add_fluid(datetime.datetime.now() + datetime.timedelta(days=1))