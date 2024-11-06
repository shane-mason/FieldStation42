import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.DEBUG)

from fs42.catalog import ShowCatalog, MatchingContentNotFound, NoFillerContentFound
from fs42.show_block import ShowBlock, ClipBlock, MovieBlocks
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2, OPERATING_HOURS
import pickle
import json
import os
import glob
import random
import datetime
import argparse

class Station42:

    def __init__(self, config, rebuild_catalog=False):
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        self.catalog = ShowCatalog(self.config, rebuild_catalog=rebuild_catalog)
        #self.catalog.print_catalog()

    def _write_json(self, clips, day_name, time_slot):

        #first, ensure the runtime_dir exists
        if not os.path.isdir(self.config['runtime_dir']):
            #then lets try and make it
            try:
                os.mkdir(self.config['runtime_dir'])
                self._l.info(f"Directory '{self.config['runtime_dir']}' created successfully.")
            except FileExistsError:
                self._l.info(f"Directory '{self.config['runtime_dir']}' already exists - we should be fine")
            except PermissionError:
                self._l.error(f"Permission denied: Unable to create '{self.config['runtime_dir']}'.")
            except Exception as e:
                self._l.error(f"An error occurred: {e}")
                raise (f"Runtime folder not found and failed to create - something is wrong with your configuration.")

        as_json = json.dumps(clips, indent=4)
        out_path = f"{self.config['runtime_dir']}/{day_name}_{time_slot}.json"
        with open(out_path, "w") as f:
            f.write(as_json)

    def write_day_to_playlist(self, schedule, day_name):
        for h in OPERATING_HOURS:
            t_slot = str(h)
            if t_slot in schedule:
                try:
                    if isinstance(schedule[t_slot], MovieBlocks):
                        back_hour = h+1
                        if back_hour >= 24:
                            back_hour = 0
                        (plan_a, plan_b) = schedule[t_slot].make_plans()
                        self._write_json(plan_a, day_name, t_slot)
                        self._write_json(plan_b, day_name, str(back_hour))
                    else:
                        clips = schedule[t_slot].make_plan()
                        self._write_json(clips, day_name, t_slot)
                except:
                    self._l.error("Error writing playlist - likely an error in the catalog or configuration")
                    self._l.error(f"Check schedule for day: {day_name} at {t_slot}")
                    raise Exception("Error writing schedule")


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

        return ClipBlock('signoff', clips, HOUR-remaining_time)

    def make_offair_hour(self):
        remaining_time = HOUR
        clips=[]
        if 'off_air_video' in self.config:
            oa = self.catalog.get_offair()
            #fill the rest with offair
            while remaining_time > oa.duration:
                clips.append(oa)
                remaining_time -= oa.duration

        return ClipBlock('signoff', clips, HOUR-remaining_time)

    def make_weekly_schedule(self):
        schedule = {}
        now = datetime.datetime.now()
        schedule['gen_time'] = now

        to_remove = glob.glob(f"{self.config['runtime_dir']}/*")
        for f in to_remove:
            os.remove(f)

        day_number = 0
        real_day = now.weekday()
        for day_name in DAYS:
            day_offset = day_number - real_day
            delta = datetime.timedelta(days=day_offset)
            when = now + delta
            self._l.info(f"Making schedule for {day_name} {when.date()}")

            schedule[day_name] = self.make_daily_schedule(day_name, when)
            self.write_day_to_playlist(schedule[day_name], day_name)
            day_number += 1

        with open(self.config['schedule_path'], 'wb') as f:
            pickle.dump(schedule,f)

        self._l.info(f"Wrote output to {self.config['schedule_path']}")



    def make_daily_schedule(self, day_str, when):
        schedule = {}
        day = self.config[day_str]
        skip_next = False
        # go through each possible hour in a day
        for h in OPERATING_HOURS:
            when = when.replace(hour=h)
            if not skip_next:
                slot = str(h)
                if slot in day:
                    if 'tags' in day[slot]:
                        tag = day[slot]['tags']
                        if tag in self.config['clip_shows']:
                            # then this is a clip show
                            schedule[slot] = self.make_clip_hour(tag, when)
                        elif 'two_hour' in self.config and tag in self.config['two_hour']:
                            schedule[slot] = self.make_double_schedule(tag, when)
                            skip_next = True
                        else:
                            # then this is a single hour show
                            schedule[slot] = self.make_hour_schedule(tag, when)

                    if 'event' in day[slot]:
                        if day[slot]['event'] == "signoff" and 'sign_off_video' in self.config:
                            schedule[slot] = self.make_signoff_hour()
                else:
                    #then we are off off_air
                    if 'off_air_video' in self.config:
                        schedule[slot] = self.make_offair_hour()
            else:
                skip_next = False


        return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='FieldStation42 Catalog and Schedule Generation')
    parser.add_argument('--rebuild_catalog', action='store_true', help='Overwrite catalog if it exists')

    args = parser.parse_args()
    from confs.fieldStation42_conf import main_conf
    for c in main_conf["stations"]:
        station = Station42(c, args.rebuild_catalog)
        schedule = station.make_weekly_schedule()

    print("Schedules generated - exiting FieldStation42.")







