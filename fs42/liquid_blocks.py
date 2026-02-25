import datetime
import os.path

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
            #print("break info: ", break_info)
            self.start_bump = break_info.get("start_bump", None)
            self.end_bump = break_info.get("end_bump", None)
            self.bump_override = break_info.get("bump_dir", None)
            self.commercial_override = break_info.get("commercial_dir", None)
        
        self.break_strategy = break_strategy

    def __str__(self):
        content = os.path.basename(self.content.path)
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title} - {content}"

    def content_duration(self):
        return self.content.duration

    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    @staticmethod
    def clip_break_points(break_points, max_breaks, content_duration):
        # ensure start ordering
        break_points = MediaProcessor.calc_black_segments(break_points, content_duration)

        # Handle edge cases
        if max_breaks <= 0 or len(break_points) == 0:
            return []

        if len(break_points) <= max_breaks:
            return break_points

        # Merge adjacent chapters to create evenly-distributed segments
        # This ensures no content is skipped, just fewer commercial breaks
        max_breaks = int(max_breaks)

        # Calculate which chapter boundaries to keep as break insertion points
        # For max_breaks segments, we need (max_breaks - 1) commercial breaks
        num_breaks = max_breaks - 1

        # Select evenly-distributed break positions
        step = (len(break_points) - 1) / num_breaks if num_breaks > 0 else 0
        break_indices = []
        for i in range(1, max_breaks):  # Start from 1, not 0 (skip the first chapter start)
            index = round(i * step)
            if index not in break_indices and index < len(break_points):
                break_indices.append(index)

        # Create merged segments by combining chapters between selected break points
        merged_segments = []
        segment_start_idx = 0

        for break_idx in break_indices:
            # Merge all chapters from segment_start_idx to break_idx into one segment
            merged_segment = {
                "chapter_start": break_points[segment_start_idx]["chapter_start"],
                "chapter_end": break_points[break_idx]["chapter_start"],
            }
            merged_segments.append(merged_segment)
            segment_start_idx = break_idx

        # Add the final segment (from last break to end)
        final_segment = {
            "chapter_start": break_points[segment_start_idx]["chapter_start"],
            "chapter_end": break_points[-1]["chapter_end"],
        }
        merged_segments.append(final_segment)

        return merged_segments

    def make_plan(self, catalog):
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        _fluid = FluidBuilder()

        # Prefer chapter markers over black detection
        break_points = _fluid.get_chapters(self.content.realpath)
        if not break_points:
            # Fall back to black detection if no chapters
            break_points = _fluid.get_breaks(self.content.realpath)

        strict_count = None
        if break_points:
            # Calculate how many breaks we need based on break_duration config
            # If break_duration is configured, use it to determine break count
            break_duration = self.break_info.get("break_duration", None)
            if break_duration is None:
                # Try to get from catalog config if not in break_info
                break_duration = catalog.config.get("break_duration", None)

            if break_duration and break_duration > 0:
                # Calculate desired number of breaks based on total buffer and break_duration
                # This respects the user's break_duration setting
                desired_breaks = max(1, int(diff / break_duration))

                # break_points contains content segments, so we need desired_breaks + 1 segments
                desired_segments = desired_breaks + 1

                # If we have more chapter markers than needed, select the best-positioned ones
                if len(break_points) > desired_segments:
                    break_points = self.clip_break_points(break_points, desired_segments, self.content_duration())

                # strict_count is the number of reel blocks (commercial breaks) to create
                # This is one less than the number of content segments
                strict_count = len(break_points) - 1 if len(break_points) > 0 else 0
            else:
                # Fallback: limit breaks to no more than every 2 minutes of playback
                max_breaks = self.playback_duration() / timings.MIN_2
                # We need max_breaks + 1 content segments to create max_breaks commercial breaks
                max_segments = int(max_breaks) + 1

                if len(break_points) > max_segments:
                    break_points = self.clip_break_points(break_points, max_segments, self.content_duration())

                # strict_count is the number of reel blocks (one less than content segments)
                strict_count = len(break_points) - 1 if len(break_points) > 0 else 0

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump["duration"]

        if self.end_bump:
            diff -= self.end_bump["duration"]

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
                # only clip break_points if we have reel blocks to work with
                # if reel_blocks is empty (e.g., diff <= 2), we don't need chapter-based breaks
                if len(self.reel_blocks) > 0:
                    break_points = self.clip_break_points(break_points, len(self.reel_blocks), self.content_duration())
                else:
                    # no reel blocks = no buffer time = no breaks needed, clear break_points
                    break_points = []
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
            diff -= self.start_bump["duration"]

        if self.end_bump:
            diff -= self.end_bump["duration"]

        # calculate desired number of breaks based on break_duration
        strict_count = None
        break_duration = self.break_info.get("break_duration", None)
        if break_duration is None:
            break_duration = catalog.config.get("break_duration", None)

        if break_duration and break_duration > 0 and diff > 2:
            # calculate how many breaks we want based on total buffer time and break_duration
            strict_count = max(1, int(diff / break_duration))

        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise (ValueError(err))
        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time, diff, commercial_dir=self.commercial_override, bump_dir=self.bump_override, strict_count=strict_count
            )
        else:
            self.reel_blocks = []

        self.plan = ReelCutter.cut_reels_into_clips(
            self.content, self.reel_blocks, self.break_strategy, self.start_bump, self.end_bump
        )


class LiquidOffAirBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None, sign_off=None):
        super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.sign_off = sign_off

    def make_plan(self, catalog):
        self.plan = []
        current_mark = self.start_time
        first_loop = True
        while current_mark < self.end_time:
            # only show sign_off on first loop
            if self.sign_off and first_loop:
                _content = self.sign_off
            else:
                _content = self.content
            first_loop = False
            duration = float(_content.duration)
            current_mark += datetime.timedelta(seconds=duration)
            datetime.timedelta()
            if current_mark > self.end_time:
                # then we will clip it to end at end time
                delta = current_mark - self.end_time
                duration -= delta.total_seconds()

            self.plan.append(BlockPlanEntry(_content.path, 0, duration, content_type=_content.content_type, media_type=_content.media_type))


class LiquidLoopBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None):
        super().__init__(content, start_time, end_time, title, break_strategy, break_info)

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

            entries.append(BlockPlanEntry(clip.path, 0, duration, content_type=clip.content_type, media_type=clip.media_type))

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
            entries.append(BlockPlanEntry(self.start_bump.path, 0, self.start_bump.duration, content_type="bump", media_type=self.start_bump.media_type))
        for comm in self.comms:
            entries.append(BlockPlanEntry(comm.path, 0, comm.duration, content_type="commercial", media_type=comm.media_type))
        if self.end_bump is not None:
            entries.append(BlockPlanEntry(self.end_bump.path, 0, self.end_bump.duration, content_type="bump", media_type=self.end_bump.media_type))
        return entries
