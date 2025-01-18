import os
import pickle
import datetime
import sys

from fs42.station_manager import StationManager
from fs42.liquid_blocks import LiquidBlock, BlockPlanEntry

class ScheduleNotFound(Exception):
    pass

class SheduleQueryNotInBounds(Exception):
    pass

class PlayPoint():
    def __init__(self, index, offset, plan):
        self.index = index
        self.offset = offset
        self.plan:BlockPlanEntry = plan

    def __str__(self):
        return f"PlayPoint: index={self.index} offet={self.offset} plan_len={len(self.plan)}"

class LiquidManager(object):
    __we_are_all_one = {}
    stations = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(LiquidManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj
    
    def __init__(self):
        if not len(self.stations):
            self.stations =  StationManager().stations
            self._load_schedules()

    def _load_schedules(self):
        self.schedules = {}
        for station in self.stations:
            if station['network_type'] != 'guide':
                _id = station['network_name']
                _path = station['schedule_path']
                if os.path.isfile(_path):
                    with open(_path, "rb") as f:
                        try:
                            self.schedules[_id] = pickle.load(f)
                        except ModuleNotFoundError as e:
                            print('\033[91m' + "Error loading schedule - this means you probably need to update your schedule format")
                            print("Please update your schedules by running station_42.py -x and then regenerating. Cheers!" + '\033[0m')
                            sys.exit(-1)
                else:
                    self.schedules[_id] = []

    

    def get_schedule_by_name(self, network_name):
        if network_name in self.schedules:
            return self.schedules[network_name]
        else:
            return None

    def reset_all_schedules(self):
        for station in self.stations:
            if station['network_type'] != "guide":
                if os.path.exists(station["schedule_path"]):
                    os.unlink(station["schedule_path"])
        self._load_schedules()

    def get_extents(self, network_name):
        _id = network_name
        if _id not in self.schedules:
            raise(ValueError(f"Can't get extent for network named {network_name}"))
        _blocks = self.schedules[_id]
        if len(_blocks):
            return(_blocks[0].start_time, _blocks[-1].end_time)
        else:
            return (None, None)

    def get_summary(self):
        summary = ""
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summary += f"{_id} schedule extents: {s} to {e}\n"
        
        return summary
    
    def get_programming_block(self, network_name, when):
        (start, end) = self.get_extents(network_name)

        #handle no schedule
        if start is None or end is None:
            raise ScheduleNotFound(f"Schedule doesn't exist for {network_name}")
        #handle not in bounds
        elif start > when or end < when:
            raise SheduleQueryNotInBounds(f"Query for {network_name} programming at {when} failes because schedule is from {start} to {end}")
        #handle expected case
        else:
            #go through each block until we find the correct position (when > block start and < block end)
            for _block in self.schedules[network_name]:
                
                if when >= _block.start_time and when <= _block.end_time:
                    #this is it, no need to keep going
                    return _block
        
                
    def get_play_point(self, network_name, when):
        #get the block and get plan
        _block:LiquidBlock = self.get_programming_block(network_name, when)
        #find index in block plan
        found_index = 0
        current_mark = _block.start_time
        for entry in _block.plan:
            next_mark = current_mark + datetime.timedelta(seconds=entry.duration) 
            if next_mark > when:
                #then this is the index - calc offset
                diff = when - current_mark
                return PlayPoint(found_index, diff.total_seconds(), _block.plan)
            current_mark = next_mark
            found_index+=1

    def print_schedule(self, network_name, go_deep=False):
        for _block in self.schedules[network_name]:
            print(_block)
            if go_deep:
                #print(_block)
                current_mark = _block.start_time
                next_mark = current_mark
                for _entry in _block.plan:
                    next_mark = current_mark + datetime.timedelta(seconds=_entry.duration)
                    print(f"{_entry} start={current_mark.time()} end={next_mark.time()}")
                    current_mark = next_mark

  


            


