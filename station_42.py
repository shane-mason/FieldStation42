import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)

from fs42.catalog import ShowCatalog, MatchingContentNotFound, NoFillerContentFound
from fs42.schedule_builder import ScheduleBuilder
from fs42.show_block import ShowBlock, ClipBlock, MovieBlocks, ContinueBlock
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2, OPERATING_HOURS
from fs42.station_manager import StationManager
import pickle
import json
import os
import glob
import random
import datetime
import argparse

class Station42:

    def __init__(self, config, rebuild_catalog=False):
        # station configuration
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        self.catalog = ShowCatalog(self.config, rebuild_catalog=rebuild_catalog)
        self.builder = ScheduleBuilder(self.catalog, self.config)


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
        #go through each hour
        for h in OPERATING_HOURS:
            t_slot = str(h)
            # if there is a schedule for this hour
            if t_slot in schedule:
                try:
                    if isinstance(schedule[t_slot], MovieBlocks):
                        back_hour = h+1
                        if back_hour >= 24:
                            back_hour = 0
                        (plan_a, plan_b) = schedule[t_slot].make_plans()
                        self._write_json(plan_a, day_name, t_slot)
                        self._write_json(plan_b, day_name, str(back_hour))
                    elif not isinstance(schedule[t_slot], ContinueBlock):
                        clips = schedule[t_slot].make_plan()
                        self._write_json(clips, day_name, t_slot)
                except:
                    self._l.error("Error writing playlist - likely an error in the catalog or configuration")
                    self._l.error(f"Check schedule for day: {day_name} at {t_slot}")
                    raise Exception("Error writing schedule")


    def make_weekly_schedule(self):
        schedule = {}
        now = datetime.datetime.now()
        schedule['gen_time'] = now

        to_remove = glob.glob(f"{self.config['runtime_dir']}/*")
        for f in to_remove:
            os.remove(f)

        day_number = 0
        real_day = now.weekday()

        #go through each day
        for day_name in DAYS:
            # what is the offset from current to when we are making the schedule for?
            day_offset = day_number - real_day
            delta = datetime.timedelta(days=day_offset)
            when = now + delta
            self._l.debug(f"Making schedule for {day_name} {when.date()}")
            match self.config["network_type"]:
                case "standard":
                    schedule[day_name] = self._standard_daily_schedule(day_name, when)
                case "loop":
                    schedule[day_name] = self._loop_daily_schedule(day_name, when)
                case "guide":
                    raise NotImplementedError("Guide schedules are not yet supported")
                
            self.write_day_to_playlist(schedule[day_name], day_name)
            day_number += 1

        with open(self.config['schedule_path'], 'wb') as f:
            pickle.dump(schedule,f)

        self._l.info(f"Wrote schedule output to {self.config['schedule_path']}")

    def _loop_daily_schedule(self, day_str, when):
        return self.builder.make_loop_day("content", when)

    def _standard_daily_schedule(self, day_str, when):
        schedule = {}
        day = self.config[day_str]
        continue_next = None
        # go through each possible hour in a day
        for h in OPERATING_HOURS:
            when = when.replace(hour=h)
            slot = str(h)
            if not continue_next:

                if slot in day:
                    if 'tags' in day[slot]:
                        tag = day[slot]['tags']
                        if tag in self.config['clip_shows']:
                            # then this is a clip show
                            schedule[slot] = self.builder.make_clip_hour(tag, when)
                        elif 'two_hour' in self.config and tag in self.config['two_hour']:
                            schedule[slot] = self.builder.make_double_schedule(tag, when)
                            continue_next = schedule[slot].title
                        else:
                            # then this is a single hour show
                            schedule[slot] = self.builder.make_hour_schedule(tag, when)

                    if 'event' in day[slot]:
                        if day[slot]['event'] == "signoff" and 'sign_off_video' in self.config:
                            schedule[slot] = self.builder.make_signoff_hour()
                else:
                    #then we are off off_air
                    if 'off_air_video' in self.config:
                        schedule[slot] = self.builder.make_offair_hour()
            else:

                schedule[slot] = ContinueBlock(continue_next)
                continue_next = None


        return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='FieldStation42 Catalog and Schedule Generation')
    parser.add_argument('-c', '--check_catalogs', action='store_true', help='Check catalogs, print report and exit.')
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument('-p', '--printcat', help='Print the catalog for the specified network name and exit')
    parser.add_argument('-r', '--rebuild_catalog', action='store_true', help='Overwrite catalog if it exists')
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')

    args = parser.parse_args()

    if( args.verbose ):
        logging.getLogger().setLevel(logging.DEBUG)

    if (args.logfile):
        print("will be logging ", args.logfile)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    found_print_target = False

    for station_conf in StationManager().stations:
        if 'network_type' in station_conf and station_conf['network_type'] == "guide":
            logging.getLogger().info(f"Loaded guide channel")
        elif args.printcat:
            if station_conf['network_name'] == args.printcat:
                logging.getLogger().info(f"Printing catalog for {station_conf['network_name']}")
                station = Station42(station_conf, args.rebuild_catalog)
                station.catalog.print_catalog()
                found_print_target = True
        else:
            logging.getLogger().info(f"Loading catalog for {station_conf['network_name']}")
            station = Station42(station_conf, args.rebuild_catalog)
            if args.check_catalogs:
                #then just run a check and exit
                logging.getLogger().info(f"Checking catalog for {station_conf['network_name']}")
                station.check_catalog()
            else:
                logging.getLogger().info(f"Making schedule for {station_conf['network_name']}")
                schedule = station.make_weekly_schedule()



    if args.printcat and not found_print_target:
        logging.getLogger().error(f"Could not find catalog for network named: {args.printcat}")






