from fs42.liquid_blocks import LiquidBlock
from fs42.liquid_io import LiquidIO
from fs42.liquid_manager import (
    ScheduleNotFound,
    ScheduleQueryNotInBounds,
    build_stream_point,
    play_point_in_block,
)
from fs42.station_manager import StationManager


class SchedulePastEnd(ScheduleQueryNotInBounds):
    pass


class ScheduleBeforeStart(ScheduleQueryNotInBounds):
    pass


class PlayPointQuery:
    """Reads single blocks straight from the database - nothing is loaded or cached up front."""

    def __init__(self):
        self._io = LiquidIO()

    def get_extents(self, network_name):
        return self._io.get_liquid_extents(network_name)

    def get_programming_block(self, network_name, when) -> LiquidBlock | None:
        block = self._io.get_liquid_block_at(network_name, when)
        if block is not None:
            return block

        (start, end) = self.get_extents(network_name)
        if start is None:
            raise ScheduleNotFound(f"Schedule doesn't exist for {network_name}")
        if when < start:
            raise ScheduleBeforeStart(f"Query for {network_name} at {when} is before the schedule starts at {start}")
        if when > end:
            raise SchedulePastEnd(f"Query for {network_name} at {when} is after the schedule ends at {end}")
        # inside the schedule, but no block covers this moment
        return None

    def get_play_point(self, network_name, when):
        station_conf = StationManager().station_by_name(network_name)
        if station_conf["network_type"] == "streaming":
            return build_stream_point(station_conf)

        block = self.get_programming_block(network_name, when)
        if block is None:
            return None
        return play_point_in_block(block, when, station_conf)
