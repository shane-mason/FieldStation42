import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2, OPERATING_HOURS
from fs42.show_block import ShowBlock, ClipBlock, MovieBlocks, ContinueBlock, LoopBlock
from fs42.catalog import MatchingContentNotFound, NoFillerContentFound

class ScheduleBuilder():

    def __init__(self, catalog, config):
        self.catalog = catalog
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        
    def flexi_break(self, fill_time, when):
        reels = []
        remaining_time = fill_time

        keep_going = True

        while keep_going:
            try:
                fill = self.catalog.find_filler(remaining_time, when)
                remaining_time-=fill.duration
                reels.append(fill)
            except NoFillerContentFound as e:
                self._l.error("No commercials or bumps found - please add content to commercial and bump folders or check your configuration")
                raise e
            except MatchingContentNotFound:
                if(remaining_time > 30):
                    self._l.warning(f"Couldn't find commercials or bumps less than {remaining_time} seconds - FieldStation42 requires fill content to simulate accurate schedules.")
                keep_going = False

        return reels
    
    def make_loop_day(self, tag, when):
        self._l.info(f"Making loop day: {when}")
        content = self.catalog.get_all_by_tag(tag)
        content_index = 0
        schedule = {}
        previous_spill = 0
        for h in OPERATING_HOURS:
            entries = []
            when = when.replace(hour=h)
            slot = str(h)
            remaining_time = HOUR + previous_spill
            spill_time = 0
            
            #while there is still stime in the hour
            while remaining_time:
                entry = content[content_index]

                duration = entry.duration
                if duration > remaining_time:
                    #then some time spills into the next hour
                    spill_time = duration - remaining_time
                    remaining_time = 0
                    #leave content index as is, so it is the next one
                else:
                    remaining_time -= duration
                    
                    content_index+=1
                    if content_index >= len(content):
                        content_index = 0
                
                entries.append(entry)    
            
            
            block = LoopBlock("Informational", entries, previous_spill)
            previous_spill = spill_time

            schedule[slot] = block
        return schedule

    def make_hour_schedule(self, tag, when):
        remaining_time = HOUR
        reels = [] 
        front = None
        back_half = None

        #this limits us to 24 hour program length
        candidate = self.catalog.find_candidate(tag, HOUR, when)
        if candidate:
            front = candidate
            front.count+=1
            remaining_time-=candidate.duration
            if front.duration > HOUR:
                slot_continues = front.duration - HOUR
                raise NotImplementedError("Video must be under one hour or in a directory marked for longer, like 'two_hour' " )

            if remaining_time > H_HOUR:
                #then ask for another half hour
                back_half = self.catalog.find_candidate(tag, H_HOUR, when)
                if back_half:
                    remaining_time-=back_half.duration
                else:
                    self._l.error("Error getting candidate for back slot")
                    raise Exception(f"Error making schedule for tag: {tag}")

        else:
            self._l.error("Error getting candidate for slot.")
            raise Exception(f"Error making schedule for tag: {tag}")


        reels = self.flexi_break(remaining_time, when)
        return ShowBlock(front, back_half, reels)

    def make_double_schedule(self, tag, when):
        remaining_time = HOUR2
        candidate = self.catalog.find_candidate(tag, HOUR*2, when)
        reels = []
        if candidate:
            remaining_time-=candidate.duration
        else:
            self._l.error("Error getting candidate for double slot")
            raise Exception(f"Error making schedule for tag: {tag}")

        reels = self.flexi_break(remaining_time, when)
        return MovieBlocks(candidate, reels, tag)

    def make_clip_hour(self, tag, when):
        remaining_time = HOUR
        more_candidates = True
        clips = []
        while remaining_time > MIN_5 and more_candidates:
            candidate=self.catalog.find_candidate(tag, remaining_time, when)
            if candidate:
                clips.append(candidate)
                remaining_time -= candidate.duration
                #make a standard commercial break
                for i in range(4):
                    if remaining_time > 15:
                        fill = self.catalog.find_filler(remaining_time, when)
                        clips.append(fill)
                        remaining_time -= fill.duration
            else:
                more_candidates = False

        reels = self.flexi_break(remaining_time, when)

        return ClipBlock(tag, clips, HOUR-remaining_time)

    def make_signoff_hour(self):
        remaining_time = HOUR
        so = self.catalog.get_signoff()
        clips = [so]
        remaining_time -= so.duration

        if 'off_air_video' in self.config:
            oa = self.catalog.get_offair()
            #fill the rest with offair
            while remaining_time > oa.duration:
                clips.append(oa)
                remaining_time -= oa.duration                
        
            #go over the hour so it can be snipped to duration
            if remaining_time > 0:
                clips.append(oa)

        return ClipBlock('signoff', clips, duration=HOUR, snip_to_duration=True)

    def make_offair_hour(self):
        remaining_time = HOUR
        clips=[]
        if 'off_air_video' in self.config:
            oa = self.catalog.get_offair()
            #fill the rest with offair
            while remaining_time > oa.duration:
                clips.append(oa)
                remaining_time -= oa.duration

            #go over the hour so it can be snipped to duration
            if remaining_time > 0:
                clips.append(oa)

        return ClipBlock('offair', clips, duration=HOUR, snip_to_duration=True)
