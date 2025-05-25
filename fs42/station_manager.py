import json
import logging
import os
from fs42.slot_reader import SlotReader
import glob

class StationManager(object):

    __we_are_all_one = {}
    
    stations = []

    overwatch = {"network_type": "standard",
                "schedule_increment": 30,  
                "break_strategy": "standard",
                "commercial_free": False,
                "clip_shows": [],
                "break_duration": 120}

    filechecks = ["sign_off_video", "off_air_video", "standby_image"]

    main_config = "confs/main_config.json"

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(StationManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj
    
    def __init__(self):
        if not len(self.stations):
            self.server_conf = {"channel_socket": "runtime/channel.socket",
                                "status_socket": "runtime/play_status.socket",
                                "day_parts" : {
                                    "morning"  : range(6,10),
                                    "daytime"  : range(10,18),
                                    "prime"    : range(18,23),
                                    "late"     : [23,0, 1, 2],
                                    "overnight": range(2, 6) 
                                    }
                                }
            self.load_main_config()
            self.load_json_stations()
        
        for i in range(len(self.stations)):
            station = self.stations[i]
            if station['network_type'] == "standard":
                self.stations[i] = SlotReader.smooth_tags(station)

    def station_by_name(self, name):
        for station in self.stations:
            if station["network_name"] == name:
                return station
        return None
    
    def station_by_channel(self, channel):
        for station in self.stations:
            if station["channel_number"] == channel:
                return station
        return None

    def index_from_channel(self, channel):
        index = 0
        for station in self.stations:
            if station["channel_number"] == channel:
                return index
            index+=1
        return None

    def get_day_parts(self):
        return self.server_conf["day_parts"]

    def load_main_config(self):
        _l = logging.getLogger("STATIONMANAGER")
        if os.path.exists(StationManager.main_config):
            with open(StationManager.main_config) as f:
                try:
                    d = json.load(f)
                    if "channel_socket" in d:
                        self.server_conf["channel_socket"] = d["channel_socket"]
                    if "status_socket" in d:
                        self.server_conf["status_socket"] = d["status_socket"]
                    if "day_parts" in d:
                        new_parts = {}
                        for key in d["day_parts"]:
                            start_hour = d["day_parts"][key]["start_hour"]
                            end_hour = d["day_parts"][key]["end_hour"]
                            if end_hour > start_hour:
                                new_parts[key] = range(start_hour, end_hour)
                            else:
                                #wraps midnight - manually build the list of hours
                                hours = []
                                hour = start_hour
                                while hour <= 23:
                                    hours.append(hour)
                                    hour+=1
                                hour = 0
                                while hour <= end_hour:
                                    hours.append(hour)
                                    hour+=1
                                new_parts[key] = hours
                        self.server_conf["day_parts"] = new_parts

                except Exception as e:
                    print(e)
                    _l.exception(e)
                    _l.error(f"Error loading main config overrides from {StationManager.main_config}")
                    exit(-1)
        # else skip, no over rides

    def load_json_stations(self): 
        _l = logging.getLogger("STATIONMANAGER")
        cfiles = glob.glob("confs/*.json")
        station_buffer = []
        for fname in cfiles:
            if fname != StationManager.main_config:
                with open(fname) as f:
                    try:
                        d = json.load(f)
                        #set defaults for optionals
                        for key in StationManager.overwatch:
                            if key not in d['station_conf']:
                                d['station_conf'][key] = StationManager.overwatch[key]

                        for to_check in StationManager.filechecks:
                            if to_check in d['station_conf']:
                                if not os.path.exists(d['station_conf'][to_check]):
                                    _l.error("*" * 60)
                                    _l.error(f"Error while checking configuration for {fname}")
                                    _l.error(f"The filepath specified for {to_check} does not exist: {d['station_conf'][to_check]}")
                                    _l.error("*" * 60)
                                    exit(-1)

                        station_buffer.append(d['station_conf'])
                    except Exception as e:
                        _l.error("*" * 60)
                        _l.error(f"Error loading station configuration: {fname}")
                        _l.exception(e)
                        _l.error("*" * 60)
                        exit(-1)

        self.stations = sorted(station_buffer, key=lambda station: station['channel_number'])

