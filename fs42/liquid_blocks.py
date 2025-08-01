import datetime

from fs42 import timings
from fs42.reel_cutter import ReelCutter
from fs42.block_plan import BlockPlanEntry
from fs42.fluid_builder import FluidBuilder
from fs42.media_processor import MediaProcessor


class LiquidBlock:
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None):
        self.content = content
        # the requested starting time
        self.start_time = start_time
        # the expected/requested end time
        self.end_time = end_time
        if title is None and type(content) is not list:
            self.title = content.title
        else:
            self.title = title
        self.reel_blocks = None
        self.plan = None
        

        self.break_info = break_info if break_info else {}
        
        self.sequence_key = None

        if break_info:
            self.start_bump = break_info.get("start_bump", None)
            self.end_bump = break_info.get("end_bump", None)
            self.bump_override = break_info.get("bump_dir", None)
            self.commercial_override = break_info.get("commercial_dir", None)
        
        self.break_strategy = break_strategy

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"

    def content_duration(self):
        return self.content.duration

    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    @staticmethod
    def clip_break_points_dist(break_points, max_breaks):
        # then remove the ones with the shortest durations until we have fewer than max_breaks
        sorted_breaks = sorted(break_points, key=lambda k: k["black_duration"], reverse=True)
        clipped_breaks = sorted_breaks[: int(max_breaks)]
        # and put it back in place
        break_points = sorted(clipped_breaks, key=lambda k: k["black_start"])
        return break_points

    @staticmethod
    def clip_break_points(break_points, max_breaks, content_duration):
        # ensure start ordering
        break_points = MediaProcessor.calc_black_segments(break_points, content_duration)

        # then remove the ones with the shortest segment duration until we have fewer than max_breaks
        sorted_breaks = sorted(break_points, key=lambda k: k["segment_duration"], reverse=True)
        clipped_breaks = sorted_breaks[: int(max_breaks)]
        # and put it back in place
        break_points = sorted(clipped_breaks, key=lambda k: k["black_start"])
        return break_points

    def make_plan(self, catalog):
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        _fluid = FluidBuilder()
        break_points = _fluid.get_breaks(self.content.path)
        strict_count = None
        if break_points:
            # the maximum number of breaks points should be no more than every 2 minutes
            max_breaks = self.playback_duration() / timings.MIN_2
            # or the max breaks points should make them last at least one minute each
            # max_breaks = diff/timings.MIN_1

            if len(break_points) > max_breaks:
                break_points = self.clip_break_points(break_points, max_breaks, self.content_duration())

            strict_count = len(break_points) + 1

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump.duration

        if self.end_bump:
            diff -= self.end_bump.duration

        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise (ValueError(err))

        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time,
                diff,
                commercial_dir=self.commercial_override,
                bump_dir=self.bump_override,
                strict_count=strict_count,
            )

        else:
            self.reel_blocks = []

        if strict_count:
            rec = 0
            for reel in self.reel_blocks:
                rec += reel.duration

            if strict_count == len(self.reel_blocks):
                pass
            elif strict_count > len(self.reel_blocks):
                break_points = self.clip_break_points(break_points, len(self.reel_blocks), self.content_duration())
            else:
                # do nothing for now, they will play at end
                pass

        self.plan = ReelCutter.cut_reels_into_base(
            base_clip=self.content,
            reel_blocks=self.reel_blocks,
            base_offset=0,
            base_duration=self.content_duration(),
            break_strategy=self.break_strategy,
            start_bump=self.start_bump,
            end_bump=self.end_bump,
            break_points=break_points,
        )


class LiquidClipBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None):
        if type(content) is list:
            super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        else:
            raise (TypeError(f"LiquidClipBlock required content of type list. Got {type(content)} instead"))

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"

    def content_duration(self):
        dur = 0
        for clip in self.content:
            dur += clip.duration
        return dur

    def make_plan(self, catalog):
        self.plan = []
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump.duration

        if self.end_bump:
            diff -= self.end_bump.duration

        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise (ValueError(err))
        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time, diff, commercial_dir=self.commercial_override, bump_dir=self.bump_override
            )
        else:
            self.reel_blocks = []

        self.plan = ReelCutter.cut_reels_into_clips(
            self.content, self.reel_blocks, self.break_strategy, self.start_bump, self.end_bump
        )


class LiquidOffAirBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", bump_info=None):
        super().__init__(content, start_time, end_time, title)

    def make_plan(self, catalog):
        self.plan = []
        current_mark = self.start_time

        while current_mark < self.end_time:
            duration = self.content.duration
            current_mark += datetime.timedelta(seconds=duration)
            datetime.timedelta()
            if current_mark > self.end_time:
                # then we will clip it to end at end time
                delta = current_mark - self.end_time
                duration -= delta.total_seconds()

            self.plan.append(BlockPlanEntry(self.content.path, 0, duration))


class LiquidLoopBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", bump_info=None):
        super().__init__(content, start_time, end_time, title)

    def make_plan(self, catalog):
        if not self.content:
            raise ValueError("LiquidLoopBlock requires content")
        entries = []
        keep_going = True
        current_mark: datetime.datetime = self.start_time
        next_mark: datetime.datetime = None
        current_index = 0
        while keep_going:
            clip = self.content[current_index]
            next_mark = current_mark + datetime.timedelta(seconds=clip.duration)
            duration = clip.duration
            if next_mark < self.end_time:
                current_index += 1
                if current_index >= len(self.content):
                    current_index = 0
            else:
                keep_going = False
                duration = (self.end_time - current_mark).total_seconds()

            entries.append(BlockPlanEntry(clip.path, 0, duration))

            current_mark = next_mark
        self.plan = entries


class ReelBlock:
    def __init__(self, start_bump=None, comms=[], end_bump=None):
        self.start_bump = start_bump
        self.comms = comms
        self.end_bump = end_bump

    def __str__(self):
        return f"ReelBlock: {self.duration} {len(self.comms)}"

    @property
    def duration(self):
        dur = 0
        if self.start_bump is not None:
            dur += self.start_bump.duration
        for comm in self.comms:
            dur += comm.duration
        if self.end_bump is not None:
            dur += self.end_bump.duration
        return dur

    def make_plan(self):
        entries = []
        if self.start_bump is not None:
            entries.append(BlockPlanEntry(self.start_bump.path, 0, self.start_bump.duration))
        for comm in self.comms:
            entries.append(BlockPlanEntry(comm.path, 0, comm.duration))
        if self.end_bump is not None:
            entries.append(BlockPlanEntry(self.end_bump.path, 0, self.end_bump.duration))
        return entries
