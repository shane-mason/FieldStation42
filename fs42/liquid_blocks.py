
from fs42.catalog import ShowCatalog

class LiquidBlock():

    def __init__(self, content, start_time, end_time):
        self.content = content
        #the requested starting time
        self.start_time = start_time
        #the expected/requested end time
        self.end_time = end_time

    def content_duration(self):
        return self.content.duration
    
    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    def make_plan(self, catalog:ShowCatalog):
        diff = self.playback_duration() - self.content_duration()
        reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise(ValueError(err))
        if diff > 2: 
            reel_blocks = catalog.make_reel_fill(self.start_time, diff)
        
        return reel_blocks

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

class LiquidOffAirBlock(LiquidBlock):

    def __init__(self, content, start_time, end_time):
        super().__init__(content, start_time, end_time)
