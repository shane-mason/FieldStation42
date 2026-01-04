import datetime
import logging

from fs42.station_manager import StationManager
from fs42.liquid_blocks import LiquidBlock, BlockPlanEntry
from fs42.catalog import ShowCatalog
from fs42.sequence_api import SequenceAPI
from fs42.liquid_api import LiquidAPI


class ScheduleQueryNotInBounds(Exception):
    pass


class ScheduleNotFound(Exception):
    pass


class PlayPoint:
    def __init__(self, index, offset, plan, block_title="Unknown"):
        self.index = index
        self.offset = offset
        self.plan: BlockPlanEntry = plan
        self.block_title = block_title

    def __str__(self):
        return f"PlayPoint: title={self.block_title} index={self.index} offet={self.offset} plan_len={len(self.plan)}"


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
                self.schedules[_id] = LiquidAPI.get_blocks(station)

    def get_schedule_by_name(self, network_name):
        if network_name in self.schedules:
            return self.schedules[network_name]
        else:
            return None

    def reset_all_schedules(self):
        for station_config in self.station_configs:
            if station_config["_has_schedule"]:
                logging.getLogger("liquid").info(f"Deleting schedules for {station_config['network_name']}")
                self.reset_sequences(station_config)
                LiquidAPI.delete_blocks(station_config)
        self.reload_schedules()

    def reset_schedule(self, station_config, force=False):
        
        if station_config["_has_schedule"]:
            logging.getLogger("liquid").info(f"Deleting schedules for {station_config['network_name']}")
            if not force:
               self.reset_sequences(station_config)
            LiquidAPI.delete_blocks(station_config)
        self.reload_schedules()

    def reset_sequences(self, station_config):
        logging.getLogger("liquid").info(f"Resetting sequences for {station_config['network_name']}")
        # get the catalog
        catalog = ShowCatalog(station_config)

        _blocks: list[LiquidBlock] = self.schedules[station_config["network_name"]]

        now = datetime.datetime.now()
        _reaped = {}

        # make a sequence cache index
        all_seq_list = SequenceAPI.get_sequences_for_station(station_config)
        seq_index = {}
        for this_seq in all_seq_list:
            key = (this_seq.sequence_name, this_seq.tag_path)
            if key not in seq_index:
                seq_index[key] = this_seq

        for _block in _blocks:
            # are we to now yet?
            if _block.start_time > now:
                # does it have a sequence and is that sequence in the catalog?

                if _block.sequence_key:
                    # make sure its in the store
                    #seq = SequenceAPI.get_sequence(
                    #    station_config, _block.sequence_key["sequence_name"], _block.sequence_key["tag_path"]
                    #)

                    # get the sequence from the index
                    skey = (_block.sequence_key["sequence_name"], _block.sequence_key["tag_path"])
                    seq = seq_index.get(skey, None)

                    # have we found it before?
                    if seq and skey not in _reaped:
                        # register that we found it
                        _reaped[skey] = _block

                        SequenceAPI.reset_by_episode_path(
                            station_config,
                            _block.sequence_key["sequence_name"],
                            _block.sequence_key["tag_path"],
                            _block.content.path,
                        )

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

    def get_summary_json(self, network_name=None):
        if network_name:
            (s, e) = self.get_extents(network_name)
            return {"network_id": network_name, "start": s.isoformat() if s else None, "end": e.isoformat() if e else None}

        summaries = []
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summaries.append({"network_id": _id, "start": s.isoformat() if s else None, "end": e.isoformat() if e else None})

        return summaries

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
            bpe = BlockPlanEntry(stream["url"], 0, stream["duration"], is_stream=True, content_type="stream", media_type=stream.get("media_type", "video"))
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
                return PlayPoint(found_index, diff.total_seconds(), _block.plan, _block.title)
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
