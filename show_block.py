from timings import *
import logging
from moviepy.editor import VideoFileClip, concatenate_videoclips

class ClipBlock:
    def __init__(self, name, clips, duration=HOUR):
        self.name = name
        self.duration = duration
        self.tag = f"CL.{self.name}"
        self.clips = clips


    def make_plan(self):
        _plan = []
        for clip in self.clips:
            entry = ShowBlock._entry(clip.path, 0, clip.duration)
            _plan.append(entry)
        return _plan

    def duration(self):
        dur = 0
        for clip in clips:
            dur += clip.duration
        return dur

class ShowBlock:
    def __init__(self, front=None, back=None, reels=None):
        self.front = front
        self.back = back
        self.reels = reels
        self._l = logging.getLogger(f"SHOW:")
        self.cut_timings = []

    def __str__(self):
        as_str =  f"ShowBlock: {self.duration()}s"
        as_str += f"\n--{self.front}"
        as_str += f"\n--{self.back}"
        as_str += f"\n--{len(self.reels) } @{self.reel_duration()}s\n"
        return as_str

    def _entry(path, start, duration):
        return {'path':path, 'start':start, 'duration':duration}

    def duration(self):
        total_duration = self.front.duration
        if self.back:
            total_duration += self.back.duration

        total_duration += self.reel_duration()
        return total_duration

    def reel_duration(self):
        reel_duration = 0
        for r in self.reels:
            reel_duration += r.duration
        return reel_duration

    def make_plan(self):
        self._l.debug(f"Making plan for {self.front} - {len(self.reels)}" )
        #first, get the length of the reels part
        reel_duration = self.reel_duration()
        total_duration = self.duration()

        if reel_duration < MIN_2:
            #then just put them at the end
            self._l.debug("**************Is an end plan")
            return self.make_end_plan()
        elif reel_duration < MIN_5:
            #then center and end cap
            self._l.debug("**************Is a center plan")
            return self.make_center_plan()
        else:
            self._l.debug("**************Is a full plan")
            #then we have enough to intermingle at intervals
            return self.make_full_plan()


    def make_end_plan(self):
        clips = []

        self._l.debug(f"Laying down front of block: {self.front}")
        #start at beginning and play full clip
        clips.append(ShowBlock._entry(self.front.path, 0, self.front.duration))

        # follow with back, if it exists
        if self.back:
            #are there enough reels to add a center bridge?
            if(len(self.reels) > 4):
                self._l.debug("Making center bridge")
                #then use 3 of them for the center
                for i in range(3):
                    #pop them so they aren't used in end cap
                    reel = self.reels.pop()
                    self._l.debug(f"Stacking: {reel}")
                    clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

            self._l.debug(f"Laying down back block in full: {self.back}")
            clips.append(ShowBlock._entry(self.back.path, 0, self.back.duration))
        for r in self.reels:
            self._l.debug(f"Stacking: {r}")
            clips.append(ShowBlock._entry(r.path, 0, r.duration))

        return clips

    def make_center_plan(self):
        clips = []
        #clips.append(VideoFileClip())
        half = int(len(self.reels)/2)
        front_reels = self.reels[:half]
        back_reels = self.reels[half:]
        if not self.back:
            self._l.debug(f"Laying down first half of episode: {self.front}")
            center_point = self.front.duration - MIN_1
            self._l.debug(f"Cutting break at {center_point}")
            clips.append(ShowBlock._entry(self.front.path, 0, center_point))
            for reel in front_reels:
                self._l.debug(f"Stacking {reel}")
                clips.append(ShowBlock._entry(reel.path, 0, reel.duration))
            self._l.debug(f"Laying down second half of episode: {self.back}")
            #go back to center point and then play for that long to get to end
            clips.append(ShowBlock._entry(self.front.path, center_point, center_point))
        else:
            self._l.debug(f"Laying down front episode: {self.front}")
            clips.append(ShowBlock._entry(self.front.path, 0, self.front.duration))
            self._l.debug(f"Cutting break between episodes")
            for reel in front_reels:
                self._l.debug(f"Stacking {reel}")
                clips.append(ShowBlock._entry(reel.path, 0, reel.duration))
            self._l.debug(f"Laying down second episode: {self.back}")
            clips.append(ShowBlock._entry(self.back.path, 0, self.back.duration))
        for reel in back_reels:
            self._l.debug(f"Stacking {reel}")
            clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

    def make_full_plan(self):

        if self.back:
            return self.make_half_plans()
        else:
            return self.make_hour_plan()


    def make_hour_plan(self):
        clips=[]
        self._l.debug(f"Plan full episode with breaks {self.front}")
        #6 interal breaks and the end cap
        break_count = 6
        interval = self.front.duration/break_count
        reels_per = int(len(self.reels)/break_count)
        reel_count = 0
        last_clip = 0
        clip_point = 0
        for i in range(1,break_count):
            clip_point = interval*i
            self._l.debug(f"Clipping show from {last_clip} to {clip_point}")
            clips.append(ShowBlock._entry(self.front.path, last_clip, interval))
            last_clip = clip_point
            for j in range(reels_per):
                reel = self.reels.pop()
                self._l.debug(f"Stacking: {reel}")
                clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        self._l.debug(f"Clipping show from {last_clip} to the end")
        clips.append(ShowBlock._entry(self.front.path, last_clip, self.front.duration - last_clip))
        self._l.debug("Making end cap")
        for reel in self.reels:
            self._l.debug(f"Stacking: {reel}")
            clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        return clips

    def make_half_plans(self):
        clips = []
        self._l.debug(f"Plan 2 episodes with breaks {self.front}")
        #2 interal breaks per, a middle and the end cap
        break_count = 3
        interval = self.front.duration/break_count
        reels_per = int(len(self.reels)/(break_count*2))
        clip_point = 0
        last_clip = 0

        for i in range(1,break_count):
            clip_point = interval*i
            self._l.debug(f"Clipping front episode from {last_clip} to {clip_point}")
            clips.append(ShowBlock._entry(self.front.path, last_clip, interval))
            last_clip = clip_point
            for j in range(reels_per):
                reel = self.reels.pop()
                self._l.debug(f"Stacking: {reel}")
                clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        self._l.debug(f"Clipping front episode from {last_clip} to end")
        clips.append(ShowBlock._entry(self.front.path, last_clip, self.front.duration - last_clip))

        self._l.debug("Adding middle bridge")
        for j in range(reels_per):
            reel = self.reels.pop()
            self._l.debug(f"Stacking: {reel}")
            clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        interval = self.front.duration/break_count
        last_clip = 0
        clip_point = 0
        for i in range(1,break_count):
            clip_point = interval*i
            self._l.debug(f"Clipping back episode from {last_clip} to {clip_point}")
            clips.append(ShowBlock._entry(self.back.path, last_clip, interval))
            last_clip = clip_point
            for j in range(reels_per):
                reel = self.reels.pop()
                self._l.debug(f"Stacking: {reel}")
                clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        self._l.debug(f"Clipping back episode from {last_clip} to end")
        clips.append(ShowBlock._entry(self.back.path, last_clip, self.back.duration-last_clip))
        self._l.debug("Making end cap")
        for reel in self.reels:
            self._l.debug(f"Stacking: {reel}")
            clips.append(ShowBlock._entry(reel.path, 0, reel.duration))

        return clips
