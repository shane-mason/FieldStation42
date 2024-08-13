import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.DEBUG)

from catalog import ShowCatalog
from show_block import ShowBlock, ClipBlock

import pickle
import json
import os
import glob
import random
import datetime
from timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS

#started 4:41

class Station42:

    def __init__(self, config):
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        self.catalog = ShowCatalog(self.config)
        #self.catalog.print_catalog()
        #self.make_schedule(self.config['tuesday'])


    def write_day_to_playlist(self, schedule, day_name):
        for t_slot in range(25):
            if t_slot in schedule:
                try:
                    clips = schedule[t_slot].make_plan()
                except:
                    self._l.error("Error writing playlist - likely an error in the catalog or configuration")
                    self._l.error(f"Check schedule for day: {day_name} at {t_slot}")
                    raise Exception("Error writing schedule")
                if clips:
                    as_json = json.dumps(clips, indent=4)
                    out_path = f"{self.config['runtime_dir']}/{day_name}_{t_slot}.json"
                    with open(out_path, "w") as f:
                        f.write(as_json)




    def make_hour_schedule(self, tag):
        remaining_time = HOUR
        reels = []
        front = None
        back_half = None

        #this limits us to 24 hour program length
        candidate = self.catalog.find_candidate(tag, HOUR*24)
        self._l.debug(candidate)
        if candidate:
            front = candidate
            front.count+=1
            remaining_time-=candidate.duration
            if front.duration > HOUR:
                self._l.debug("Slot continues...")
                slot_continues = front.duration - HOUR
                raise NotImplementedError("Slot continuation is not supported - video must be under one hour")

            if remaining_time > H_HOUR:
                self._l.debug("Less than half hour filled - getting back half")
                #then ask for another half hour
                back_half = self.catalog.find_candidate(tag, H_HOUR)
                if back_half:
                    remaining_time-=back_half.duration
                    self._l.debug(back_half)
                else:
                    self._l.error("Error getting candidate for back slot")
                    raise Exception(f"Error making schedule for tag: {tag}")
            else:
                self._l.debug("More than half filled - skipping back half")
        else:
            self._l.error("Error getting candidate for slot.")
            raise Exception(f"Error making schedule for tag: {tag}")

        while remaining_time > 15:
            #just add commercials and bumps
            fill = self.catalog.find_filler(remaining_time)
            if fill:
                remaining_time-=fill.duration
                reels.append(fill)

        return ShowBlock(front, back_half, reels)


    def make_clip_hour(self, tag):
        remaining_time = HOUR
        more_candidates = True
        clips = []
        while remaining_time > MIN_5 and more_candidates:
            candidate=self.catalog.find_candidate(tag, remaining_time)
            if candidate:
                clips.append(candidate)
                remaining_time -= candidate.duration
                #make a standard commercial break
                for i in range(4):
                    if remaining_time > 15:
                        fill = self.catalog.find_filler(remaining_time)
                        clips.append(fill)
                        remaining_time -= fill.duration
            else:
                more_candidates = False

        while remaining_time > 15:
            #just add commercials and bumps
            fill = self.catalog.find_filler(remaining_time)
            if fill:
                remaining_time-=fill.duration
                clips.append(fill)

        return ClipBlock(tag, clips, HOUR-remaining_time)

    def make_weekly_schedule(self):
        schedule = {}
        schedule['gen_time'] = datetime.datetime.now()

        to_remove = glob.glob(f"{self.config['runtime_dir']}/*")
        for f in to_remove:
            os.remove(f)

        for day_name in DAYS:
            self._l.debug(f"Making schedule for {day_name}")
            schedule[day_name] = self.make_schedule(day_name)
            self.write_day_to_playlist(schedule[day_name], day_name)


        with open(self.config['schedule_path'], 'wb') as f:
            pickle.dump(schedule,f)

        self._l.debug(f"Wrote output to {self.config['schedule_path']}")


    def make_schedule(self, day_str):
        schedule = {}
        slot_continues = 0
        day = self.config[day_str]
        for slot in day:
            self._l.debug("Making Slot: " + str(slot) )
            if not slot_continues:
                tag = day[slot]['tags']
                if tag in self.config['clip_shows']:
                    self._l.debug("*********************Making clip show***************************")
                    schedule[slot] = self.make_clip_hour(tag)
                else:
                    schedule[slot] = self.make_hour_schedule(tag)

            else:
                #this is a continuation
                pass

#                #print(t_slot, " - OFFAIR")
        return schedule


if __name__ == "__main__":
    from confs import nbc_conf
    from confs import abc_conf

    for c in [nbc_conf, abc_conf]:
        station = Station42(c.station_conf)
        schedule = station.make_weekly_schedule()







