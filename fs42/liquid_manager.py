import os
import pickle
import datetime
import sys

from fs42.station_manager import StationManager
from fs42.liquid_blocks import LiquidBlock, BlockPlanEntry
from fs42.catalog import ShowCatalog
from fs42 import series


class ScheduleQueryNotInBounds(Exception):
    pass


class ScheduleNotFound(Exception):
    pass


class PlayPoint:
    def __init__(self, index, offset, plan):
        self.index = index
        self.offset = offset
        self.plan: BlockPlanEntry = plan

    def __str__(self):
        return f"PlayPoint: index={self.index} offet={self.offset} plan_len={len(self.plan)}"


class LiquidManager(object):
    __we_are_all_one = {}
    _initialized = False
    station_configs = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __init__(self):
        self.__dict__ = self.__we_are_all_one
        if not self._initialized:
            self._initialized = True
            self.reload_schedules()

    def reload_schedules(self):
        self.station_configs = StationManager().stations
        self.schedules = {}
        for station in self.station_configs:
            if station["network_type"] != "guide" and station["network_type"] != "streaming":
                _id = station["network_name"]
                _path = station["schedule_path"]
                if os.path.isfile(_path):
                    with open(_path, "rb") as f:
                        try:
                            self.schedules[_id] = pickle.load(f)
                        except ModuleNotFoundError:
                            print(
                                "\033[91m"
                                + "Error loading schedule - this means you probably need to update your schedule format"
                            )
                            print(
                                "Please update your schedules by running station_42.py -x and then regenerating. Cheers!"
                                + "\033[0m"
                            )
                            sys.exit(-1)
                else:
                    self.schedules[_id] = []

    def get_schedule_by_name(self, network_name):
        if network_name in self.schedules:
            return self.schedules[network_name]
        else:
            return None

    def reset_all_schedules(self):
        for station_config in self.station_configs:
            if station_config["network_type"] != "guide" and station_config["network_type"] != "streaming":
                self.reset_sequences(station_config)
                if os.path.exists(station_config["schedule_path"]):
                    os.unlink(station_config["schedule_path"])
        self.reload_schedules()

    def reset_sequences(self, station_config):
        # get the catalog
        catalog = ShowCatalog(station_config)

        _blocks: list[LiquidBlock] = self.schedules[station_config["network_name"]]
        now = datetime.datetime.now()
        _reaped = {}

        for _block in _blocks:
            # are we to now yet?
            if _block.start_time > now:
                # does it have a sequence and is that sequence in the catalog?
                if _block.sequence_key and _block.sequence_key in catalog.sequences:
                    # have we found it before?
                    if _block.sequence_key not in _reaped:
                        # register that we found it
                        _reaped[_block.sequence_key] = _block
                        # get the sequence
                        _sequence: series.SeriesIndex = catalog.sequences[_block.sequence_key]
                        # if its a sequence, then content is a catalog entry with a path
                        print(f"resetting {_block.sequence_key}")
                        _sequence.reset_by_fpath(_block.content.path)

        catalog._write_catalog()

    def get_extents(self, network_name):
        _id = network_name
        if _id not in self.schedules:
            raise (ValueError(f"Can't get extent for network named {network_name} - it does not exist."))
        _blocks = self.schedules[_id]
        if len(_blocks):
            return (_blocks[0].start_time, _blocks[-1].end_time)
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

        # handle no schedule
        if start is None or end is None:
            raise ScheduleNotFound(f"Schedule doesn't exist for {network_name}")
        # handle not in bounds
        elif start > when or end < when:
            raise ScheduleQueryNotInBounds(
                f"Query for {network_name} programming at {when} failes because schedule is from {start} to {end}"
            )
        # handle expected case
        else:
            # go through each block until we find the correct position (when > block start and < block end)
            for _block in self.schedules[network_name]:
                if when >= _block.start_time and when <= _block.end_time:
                    # this is it, no need to keep going
                    return _block

    def _build_stream_point(self, station_conf, when):
        # get the station conf

        # get an entry
        conf_streams = station_conf["streams"]
        block_plan = []
        for stream in conf_streams:
            bpe = BlockPlanEntry(stream["url"], 0, stream["duration"], is_stream=True)
            block_plan.append(bpe)

        pp = PlayPoint(0, 0, block_plan)
        return pp

    def get_play_point(self, network_name, when):
        station_conf = StationManager().station_by_name(network_name)
        if station_conf["network_type"] == "streaming":
            return self._build_stream_point(station_conf, when)

        # get the block and get plan
        _block: LiquidBlock = self.get_programming_block(network_name, when)

        # find index in block plan
        found_index = 0
        current_mark = _block.start_time
        for entry in _block.plan:
            next_mark = current_mark + datetime.timedelta(seconds=entry.duration)
            if next_mark > when:
                # then this is the index - calc offset
                diff = when - current_mark
                return PlayPoint(found_index, diff.total_seconds(), _block.plan)
            current_mark = next_mark
            found_index += 1

    def print_schedule(self, network_name, go_deep=False):
        for _block in self.schedules[network_name]:
            print(_block)
            if go_deep:
                # print(_block)
                current_mark = _block.start_time
                next_mark = current_mark
                for _entry in _block.plan:
                    next_mark = current_mark + datetime.timedelta(seconds=_entry.duration)
                    print(f"{_entry} start={current_mark.time()} end={next_mark.time()}")
                    current_mark = next_mark
