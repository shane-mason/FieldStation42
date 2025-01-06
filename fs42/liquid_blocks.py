
import datetime

class ReelCutter:
    @staticmethod
    def cut_reels_into_base(base_clip, reel_blocks, base_offset, base_duration):
        entries = []
        break_count = 0

        if reel_blocks:
            break_count = len(reel_blocks)
        
        if break_count <= 1:
            # then don't cut the base at all
            entries.append(BlockPlanEntry(base_clip.path, base_offset, base_duration))
            if reel_blocks and len(reel_blocks) == 1:
                #and put the reel at the end if there is one
                entries += reel_blocks[0].make_plan()
        else:
            
            segment_duration = base_clip.duration / break_count
            offset = base_offset

            for i in range(break_count):
                entries.append(BlockPlanEntry(base_clip.path, offset, segment_duration))
                entries += reel_blocks[i].make_plan()
                offset += segment_duration

        return entries
    
    @staticmethod
    def cut_reels_into_clips(clips, reel_blocks, base_offset, base_duration):
        entries = []
        break_count = len(reel_blocks)
        if break_count <= 1:
            # then don't cut the base at all
            for clip in clips:
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
            if len(reel_blocks == 1):
                #and put the reel at the end if there is one
                entries += reel_blocks[0].make_plan()
        else:
            
            clips_per_segment = len(clips)/break_count

            for i in range(clips):
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
                if (i % clips_per_segment) == 0:
                    reel = reel_blocks.pop(0)
                    entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
            
            while len(reel_blocks):
                reel = reel_blocks.pop(0)
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))                

        return entries


class BlockPlanEntry:
    def __init__(self, file_path, skip=0, duration=-1):
        self.path = file_path
        self.skip = skip
        self.duration = duration

    def __str__(self):
        return f"{self.path} >> {self.skip} >> {self.duration}"
        
    
class LiquidBlock():

    def __init__(self, content, start_time, end_time):
        self.content = content
        #the requested starting time
        self.start_time = start_time
        #the expected/requested end time
        self.end_time = end_time
        self.reel_blocks = None
        self.plan = None

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.content.title}"

    def content_duration(self):
        return self.content.duration
    
    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    def make_plan(self, catalog):
        
        #first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()
        
        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise(ValueError(err))
        if diff > 2: 
            self.reel_blocks = catalog.make_reel_fill(self.start_time, diff)

        self.plan = ReelCutter.cut_reels_into_base(self.content, self.reel_blocks, 0, self.content_duration())
        

    
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
    
    def make_plan(self, catalog):   
        self.plan = []
        #first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()
        
        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise(ValueError(err))
        if diff > 2: 
            self.reel_blocks = catalog.make_reel_fill(self.start_time, diff)

        self.plan = ReelCutter.cut_reels_into_clips(self.content, self.reel_blocks, 0, self.content_duration())

class LiquidOffAirBlock(LiquidBlock):

    def __init__(self, content, start_time, end_time):
        super().__init__(content, start_time, end_time)

    def make_plan(self, catalog):
        self.plan = []
        current_mark = self.start_time
        
        while current_mark < self.end_time:
            duration = self.content.duration
            current_mark +=  datetime.timedelta(duration)
            if current_mark > self.end_time:
                #then we will clip it to end at end time
                delta = current_mark-self.end_time
                duration -= delta.total_seconds()

            self.plan.append(BlockPlanEntry(self.content.path, 0, duration))

class ReelBlock:
    def __init__(self, start_bump=None, comms=[], end_bump=None ):
        self.start_bump  = start_bump
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
            dur+= comm.duration
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