import datetime

from fs42.reel_cutter import ReelCutter
from fs42.block_plan import BlockPlanEntry

class LiquidBlock():

    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard"):
        self.content = content
        #the requested starting time
        self.start_time = start_time
        #the expected/requested end time
        self.end_time = end_time
        if title is None and type(content) is not list:
            self.title = content.title
        else:
            self.title = title
        self.reel_blocks = None
        self.plan = None
        self.break_strategy = break_strategy

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"

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
        else:
            self.reel_blocks = []

        
        self.plan = ReelCutter.cut_reels_into_base(self.content, self.reel_blocks, 0, self.content_duration(), self.break_strategy)
        

    
class LiquidClipBlock(LiquidBlock):

    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard"):
        if type(content) is list:
            super().__init__(content, start_time, end_time, title, break_strategy)
        else:
            raise(TypeError(f"LiquidClipBlock required content of type list. Got {type(content)} instead"))

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"

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
        else:
            self.reel_blocks = []
            
        self.plan = ReelCutter.cut_reels_into_clips(self.content, self.reel_blocks, 0, self.content_duration(), self.break_strategy)


class LiquidOffAirBlock(LiquidBlock):

    def __init__(self, content, start_time, end_time, title=None):
        super().__init__(content, start_time, end_time, title) 

    def make_plan(self, catalog):
        self.plan = []
        current_mark = self.start_time
        
        while current_mark < self.end_time:
            duration = self.content.duration
            current_mark +=  datetime.timedelta(seconds=duration)
            datetime.timedelta()
            if current_mark > self.end_time:
                #then we will clip it to end at end time
                delta = current_mark-self.end_time
                duration -= delta.total_seconds()

            self.plan.append(BlockPlanEntry(self.content.path, 0, duration))

class LiquidLoopBlock(LiquidBlock):
    
    def __init__(self, content, start_time, end_time, title=None):
        super().__init__(content, start_time, end_time, title)

    def make_plan(self, catalog):
        entries = []
        keep_going = True
        current_mark:datetime.datetime = self.start_time
        next_mark:datetime.datetime = None
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