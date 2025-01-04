import os
import sys
sys.path.append(os.getcwd())
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)
import pickle
import datetime
import math

from fs42.catalog import ShowCatalog
from fs42.station_manager import StationManager
from fs42.schedule_hint import TagHintReader
from fs42 import timings
from fs42.liquid_blocks import LiquidBlock, LiquidClipBlock, LiquidOffAirBlock
    
class LiquidSchedule():

    def __init__(self, conf):
        self._l = logging.getLogger("Liquid")
        self.conf = TagHintReader.smooth_tags(conf)
        self.catalog = ShowCatalog(conf)
        self._load_blocks()

    def _calc_target_duration(self, duration):
        multiple = self.conf['schedule_increment'] * 60
        if multiple == 0:
            return duration
        return multiple * math.ceil(duration / multiple)

    def _calc_target_start(self, mark):
        multiple = self.conf['schedule_increment'] * 60
        if multiple == 0:
            return mark
        return multiple * math.floor(mark / multiple)

    def _load_blocks(self):
        s_path = self.conf['schedule_path']
        if os.path.isfile(s_path):
            with open(s_path, "rb") as f:
                self._blocks = pickle.load(f)
        else:
            self._blocks = []

    def _save_blocks(self):
        with open(self.conf['schedule_path'], 'wb') as f:
            pickle.dump(self._blocks, f)

    def _end_time(self):
        if len(self._blocks) > 0:
            return self._blocks[-1].end_time
        else:
            return None

    def _fluid(self, start_time, end_target):
        new_blocks = []
        current_mark = start_time

        if current_mark is None:
            current_mark = datetime.datetime.now()

        while current_mark < end_target:
            self._l.debug(f"Making schedule for: {current_mark} {current_mark.weekday()} {current_mark.hour}")
            tag = TagHintReader.get_tag(self.conf, current_mark.weekday(), current_mark.hour)

            if tag is not None:

                candidate = self.catalog.find_candidate(tag, timings.HOUR*23, current_mark)
                if candidate is None:
                    #this should only happen on an error (have a tag, but no candidate)
                    self._l.error(f"Could not find content for tag {tag} - please add content, check your configuration and retry")
                    sys.exit(-1)
                else:
                    target_duration = self._calc_target_duration(candidate.duration)
                    next_mark = current_mark + datetime.timedelta(seconds=target_duration)
                    #TODO: Handle clip show tags
                    new_blocks.append(LiquidBlock(candidate, current_mark, next_mark))
            else:

                #then we are offair - get offair video
                candidate = self.catalog.get_offair()
                if candidate is None:
                    self._l.error(f"Schedule logic error: no schedule hints for {current_mark}")
                    self._l.error("This indicates that the station is offair, but offair content is not configured")
                    self._l.error(f"Configure 'off_air_video' or 'off_air_image' for {self.conf['network_name']}")
                    sys.exit(-1)
                
                #make it for one hour.
                next_mark = current_mark + datetime.timedelta(hours=1)
                new_blocks.append(LiquidOffAirBlock(candidate, current_mark, next_mark))

            current_mark = next_mark
        self._l.info(f"Content and reel schedules are completed")

        #now, make plans for all the blocks
        self._l.info(f"Building plans for {len(new_blocks)} new schedule blocks")
        for block in new_blocks: 
            block.make_plan(self.catalog)

        self._blocks = self._blocks + new_blocks
        self._l.info(f"Saving blocks to disk")
        self._save_blocks()
    


    def _increment(self, how_much):
        #furst, get the current end-of-schedule
        current_end = self._end_time()
        start_building = None
        end_building = None
        if current_end:
            #then there is an existing schedule
            start_building = current_end
        else:
            #then there is no schedule, so start with today (but at midnight)
            now = datetime.datetime.now()
            start_building = now.replace(hour=timings.OPERATING_HOURS[0], minute=0, second=0, microsecond=0)

        match how_much:
            case "day":
                end_building = start_building + datetime.timedelta(days=1)
            case "week":
                end_building = timings.next_week(start_building)
            case "month":
                end_building = timings.next_month(start_building)

        
        self._fluid(start_building, end_building)

    def add_days(self, day_count):
        for i in range(day_count):
            self._increment('day')

    def add_week(self):
        self._increment('week')

    def add_month(self):
        self._increment('month')
            
    def print_schedule(self):
        for block in self._blocks:
            print(block)


#print(calendar.monthrange(2024, 12))
#conf = StationManager().station_by_name("indie42")
#liq = LiquidSchedule(conf)
#start = datetime.datetime.now().replace(hour=timings.OPERATING_HOURS[0], minute=0, second=0, microsecond=0)
#datetime.datetime.now()
#liq._fluid(start, start + datetime.timedelta(hours=10000))
#liq.print_schedule()




