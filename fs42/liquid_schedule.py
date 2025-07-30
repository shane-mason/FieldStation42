import os
import sys

sys.path.append(os.getcwd())
import logging
import datetime
import math

from fs42.catalog import ShowCatalog, MatchingContentNotFound
from fs42.slot_reader import SlotReader
from fs42 import timings
from fs42.liquid_blocks import LiquidBlock, LiquidClipBlock, LiquidOffAirBlock, LiquidLoopBlock
from fs42.sequence_api import SequenceAPI
from fs42.catalog_api import CatalogAPI
from fs42.liquid_api import LiquidAPI

logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO)


class LiquidSchedule:
    def __init__(self, conf):
        self._l = logging.getLogger("Liquid")
        # self.conf = TagHintReader.smooth_tags(conf)
        self.conf = conf
        self.catalog = ShowCatalog(conf)
        self._load_blocks()

    def _calc_target_duration(self, duration, increment=None):
        # get the target duration for the show based on the shedule increment
        if increment is None:
            increment = self.conf["schedule_increment"]
        multiple = increment * 60
        if multiple == 0:
            return duration
        return multiple * math.ceil(duration / multiple)

    def _load_blocks(self):
        self._blocks = LiquidAPI.get_blocks(self.conf)

    def _save_blocks(self):
        LiquidAPI.set_blocks(self.conf, self._blocks)

    def _end_time(self):
        # get the lastest time in the schedule
        if len(self._blocks) > 0:
            return self._blocks[-1].end_time
        else:
            return None

    def _flood(self, start_time, end_target):
        # flood the schedule - this is used for loop channels
        diff = end_target - start_time
        content = self.catalog.get_all_by_tag("content")
        new_blocks = []

        programming_name = (
            self.conf["network_long_name"] if "network_long_name" in self.conf else self.conf["network_name"]
        )

        for i in range(diff.days):
            current_mark = start_time + datetime.timedelta(days=i)
            next_mark = start_time + datetime.timedelta(days=i + 1)
            block = LiquidLoopBlock(content, current_mark, next_mark, programming_name)
            new_blocks.append(block)

        self._l.info(f"Building plans for {len(new_blocks)} new schedule blocks")
        for block in new_blocks:
            block.make_plan(self.catalog)

        self._blocks = self._blocks + new_blocks
        self._save_blocks()

    def _fluid(self, start_time, end_target):
        # this is the core of the scheduler.
        new_blocks = []
        current_mark = start_time
        
        if current_mark is None:
            current_mark = datetime.datetime.now()

        while current_mark < end_target:
            self._l.debug(f"Making schedule for: {current_mark} {current_mark.weekday()} {current_mark.hour}")
            slot_config = SlotReader.get_slot(self.conf, current_mark)
            tag_str = SlotReader.get_tag_from_slot(slot_config, current_mark)

            new_block = None
            if tag_str is not None:
                break_info = {"start_bump": None, "end_bump": None, "bump_dir": None, "commercial_dir": None}

                # does this slot have a start bump?
                if "start_bump" in slot_config:
                    break_info["start_bump"] = self.catalog.get_start_bump(slot_config["start_bump"])
                if "end_bump" in slot_config:
                    break_info["end_bump"] = self.catalog.get_end_bump(slot_config["end_bump"])

                if "bump_dir" in slot_config:
                    break_info["bump_dir"] = slot_config["bump_dir"]
                else:
                    break_info["bump_dir"] = self.conf["bump_dir"]

                if "commercial_dir" in slot_config:
                    break_info["commercial_dir"] = slot_config["commercial_dir"]
                else:
                    break_info["commercial_dir"] = (
                        self.conf["commercial_dir"] if "commercial_dir" in self.conf else None
                    )

                seq_key = None

                if tag_str not in self.conf["clip_shows"]:
                    candidate = None
                    # see if this is a series with a sequence defined
                    if "sequence" in slot_config:
                        seq_name = slot_config["sequence"]

                        next_seq = SequenceAPI.get_next_in_sequence(self.conf, seq_name, tag_str)
                        if next_seq:
                            candidate = self.catalog.entry_by_fpath(next_seq.fpath)

                        seq_key = SequenceAPI.make_sequence_key(self.conf, seq_name, tag_str)
                    else:
                        candidate = self.catalog.find_candidate(tag_str, timings.HOUR * 23, current_mark)

                    if candidate is None:
                        # this should only happen on an error (have a tag, but no candidate)
                        raise MatchingContentNotFound(
                            f"Could not find content for tag {tag_str} - please add content, check your configuration and retry"
                        )

                    else:
                        _increment = slot_config.get("schedule_increment", self.conf["schedule_increment"])
                        
                        target_duration = self._calc_target_duration(candidate.duration, _increment)
                        next_mark = current_mark + datetime.timedelta(seconds=target_duration)

                        new_block = LiquidBlock(
                            candidate, current_mark, next_mark, candidate.title, self.conf["break_strategy"], break_info
                        )
                        # add sequence information
                        if seq_key:
                            new_block.sequence_key = seq_key
                else:
                    # handle clip show
                    clip_content = self.catalog.gather_clip_content(
                        tag_str, self.conf["clip_shows"][tag_str]["duration"], current_mark
                    )
                    if len(clip_content) == 0:
                        # this should only happen on an error (have a tag, but no candidate)
                        raise MatchingContentNotFound(
                            f"Could not find content for tag {tag_str} - please add content, check your configuration and retry"
                        )
                    else:
                        clip_block = LiquidClipBlock(
                            clip_content, current_mark, timings.HOUR, tag_str, self.conf["break_strategy"], break_info
                        )
                        target_duration = self._calc_target_duration(clip_block.content_duration())
                        next_mark = current_mark + datetime.timedelta(seconds=target_duration)
                        clip_block.end_time = next_mark
                        new_block = clip_block

            else:
                # then we are offair - get offair video
                candidate = self.catalog.get_offair()
                if candidate is None:
                    self._l.error(f"Schedule logic error: no time slots configured for {current_mark}")
                    self._l.error("This indicates that the station is offair, but offair content is not configured")
                    self._l.error(f"Configure 'off_air_video' or 'off_air_image' for {self.conf['network_name']}")
                    sys.exit(-1)

                # make it for one hour.
                # TODO: handle when it starts at half hour - just go to next hour (not always one hour)
                next_mark = (current_mark + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                new_block = LiquidOffAirBlock(candidate, current_mark, next_mark, "Offair")

            # here
            new_blocks.append(new_block)
            current_mark = next_mark
        self._l.info("Content and reel schedules are completed")

        # now, make plans for all the blocks and make list to update play counts
        self._l.info(f"Building plans for {len(new_blocks)} new schedule blocks")
        play_counts = []
        for block in new_blocks:
            block.make_plan(self.catalog)
            if block.content:
                # if the block has content, then we need to increment the play count
                play_counts.append(block.content)

        CatalogAPI.update_play_counts(self.conf, play_counts)

        self._blocks = self._blocks + new_blocks
        self._l.info("Saving blocks to disk")
        self._save_blocks()

    def _increment(self, how_much):
        # add time to the existing schedule
        # firsst, get the current end-of-schedule
        current_end = self._end_time()
        start_building = None
        end_building = None
        if current_end:
            # then there is an existing schedule
            start_building = current_end
        else:
            # then there is no schedule, so start with today (but at midnight)
            now = datetime.datetime.now()
            start_building = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if "schedule_offset" in self.conf:
            # then we have an offset to apply
            start_building += datetime.timedelta(minutes=self.conf["schedule_offset"])

        match how_much:
            case "day":
                end_building = start_building + datetime.timedelta(days=1)
            case "week":
                end_building = timings.next_week(start_building)
            case "month":
                end_building = timings.next_month(start_building)

        match self.conf["network_type"]:
            case "standard":
                self._fluid(start_building, end_building)
            case "loop":
                self._flood(start_building, end_building)
            case "guide":
                raise NotImplementedError("Guide channels are not yet supported for making schedules")
            case "streaming":
                # just return for now
                return

    def add_days(self, day_count):
        for i in range(day_count):
            self._increment("day")

    def add_week(self):
        self._increment("week")

    def add_month(self):
        self._increment("month")

    def add_amount(self, amount):
        self._increment(amount)

    def print_schedule(self):
        for block in self._blocks:
            print("here: " + block)
            for entry in block.plan:
                print(entry)
