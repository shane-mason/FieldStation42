import logging
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2

REELS_PER_BREAK = 6

def _entry(path, start, dur):
    return {'path':path, 'start':start, 'duration':dur}

class ReelCutter:
    
    def cut_reels_into_base(base_clip, reels, base_offset, base_duration):
        entries = []
        if len(reels) < 6:
            # just put them at the end
            entries.append(_entry(base_clip.path, base_offset, base_duration))
        elif len(reels) < 12:
            # end and center - how long are the segments?
            segment_duration = base_duration/2
            # do the first hald
            entries.append(_entry(base_clip.path, base_offset, segment_duration))
            # lay down half the reels
            for i in range(len(reels)//2):
                reel = reels.pop(0)
                entries.append(_entry(reel.path, 0, reel.duration))
            #second segment needs base offset + the first segments duration offset to start
            entries.append(_entry(base_clip.path, base_offset+segment_duration, segment_duration))
        else:
            break_count = len(reels)//REELS_PER_BREAK
            segment_duration = base_duration/break_count
            offset = base_offset
            for i in range(break_count):
                entries.append(_entry(base_clip.path, offset, segment_duration))

                for i in range(REELS_PER_BREAK):
                    reel = reels.pop(0)
                    entries.append(_entry(reel.path, 0, reel.duration))

                offset += segment_duration

        #add any remaining reels to the end
        for reel in reels:
            entries.append(_entry(reel.path, 0, reel.duration))

        return entries
    
class LoopBlock:
    def __init__(self,title, clips, spill=0):
        self.title = title
        self.clips = clips
        self.spill = spill
    
    def make_plan(self):
        entries = []
        cnt = 0
        for clip in self.clips:
            if cnt==0:
                entry = _entry(clip.path, self.spill, clip.duration-self.spill)
            else:
                entry = _entry(clip.path, 0, clip.duration)
            entries.append(entry)
            cnt+=1
        return entries



class ContinueBlock:
    def __init__(self, title):
        self.title = title

class MovieBlocks:
    def __init__(self, movie, reels, tag):
        self.movie = movie
        self.title = self.movie.title
        self.reels = reels
        self.tag = tag

    def make_plans(self):
        #how long will each segment be?
        segment_duration = self.movie.duration/2
        a_reels = self.reels[:len(self.reels)//2]
        b_reels = self.reels[len(self.reels)//2:]
        a_plan = ReelCutter.cut_reels_into_base(self.movie, a_reels, 0, segment_duration )
        b_plan = ReelCutter.cut_reels_into_base(self.movie, b_reels, segment_duration, segment_duration )
        return (a_plan, b_plan)

class ClipBlock:
    def __init__(self, name, clips, duration=HOUR, snip_to_duration=False):
        self.name = name
        self.title = name
        self._duration = duration
        self.tag = f"CL.{self.name}"
        self.clips = clips
        self.snip_to_duration = snip_to_duration


    def make_plan(self):
        _plan = []
        cur_dur = 0
        for clip in self.clips:
            cur_dur+=clip.duration
            if self.snip_to_duration and cur_dur > self._duration:
                #then this takes us over the duration so we should clip it to end at target
                clip_dur = clip.duration - (cur_dur - self._duration)
                entry = {'path':clip.path, 'start':0, 'duration':clip_dur}            
            else:
                entry = {'path':clip.path, 'start':0, 'duration':clip.duration}
            
            _plan.append(entry)
        return _plan

    @property
    def duration(self):
        if self.snip_to_duration:
            return self._duration
        else:
            dur = 0
            for clip in self.clips:
                dur += clip.duration
            return dur

class ShowBlock:
    def __init__(self, front=None, back=None, reels=None):
        self.front = front
        self.back = back
        self.reels = reels

    def make_plan(self):
        if not self.back:
            #then its just a one-hour plan
            return ReelCutter.cut_reels_into_base(self.front, self.reels, 0, self.front.duration)
        else:
            #then its 2 half hour slots
            front_reels = self.reels[:len(self.reels)//2]
            back_reels = self.reels[len(self.reels)//2:]
            front_half = ReelCutter.cut_reels_into_base(self.front, front_reels, 0, self.front.duration )
            back_half = ReelCutter.cut_reels_into_base(self.back, back_reels, 0, self.back.duration )
            full_hour = front_half + back_half
            return full_hour

