import json
import logging
import os
import glob
from fs42.slot_reader import SlotReader
from fs42 import timings


class StationManager(object):
    # the borg singleton pattern
    __we_are_all_one = {}
    _initialized = False

    # private-ish
    __overwatch = {
        "network_type": "standard",
        "schedule_increment": 30,
        "break_strategy": "standard",
        "commercial_free": False,
        "clip_shows": [],
        "break_duration": 120,
        "hidden": False 
    }

    __filechecks = ["sign_off_video", "off_air_video", "standby_image", "be_right_back_media"]

    __main_config_path = "confs/main_config.json"

    # public visible - be careful
    stations = []
    no_catalog = {"guide", "streaming", "web"}
    no_schedule = {"guide", "streaming", "web"}

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(StationManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj

    def __init__(self):
        self.__dict__ = self.__we_are_all_one
        if not self._initialized:
            self._initialized = True
            if not len(self.stations):
                self.server_conf = {
                    "channel_socket": "runtime/channel.socket",
                    "status_socket": "runtime/play_status.socket",
                    "day_parts": {
                        "morning": range(6, 10),
                        "daytime": range(10, 18),
                        "prime": range(18, 23),
                        "late": [23, 0, 1, 2],
                        "overnight": range(2, 6),
                    },
                    "time_format": "%H:%M",
                    "date_time_format": "%Y-%m-%dT%H:%M:%S",
                    "db_path": "runtime/fs42_fluid.db",
                    "start_mpv": True,
                    "server_host": "0.0.0.0",
                    "server_port": 4242,
                }
                self._number_index = {}
                self._name_index = {}
                self.load_main_config()
                self.load_json_stations()
            self.guide_config = None
            for i in range(len(self.stations)):
                station = self.stations[i]
                if station["network_type"] == "standard":
                    self.stations[i] = SlotReader.smooth_tags(station)

                if station["network_type"] == "guide":
                    self.guide_config = station
                    logging.getLogger().info("Loading and checking guide channel")
                    from fs42.guide_tk import GuideWindowConf

                    gconf = GuideWindowConf()
                    errors = gconf.check_config(station)
                    if len(errors):
                        logging.getLogger().error("Errors found in Guide Channel configuration:")
                        for err in errors:
                            logging.getLogger().error(err)
                        logging.getLogger().error("Please check your configuration and try agian.")
                        exit(-1)
                    else:
                        logging.getLogger().info("Guide channel checks completed.")

    def station_by_name(self, name):
        if name in self._name_index:
            return self._name_index[name]
        return None

    def station_by_channel(self, channel_number):
        if channel_number in self._number_index:
            return self._number_index[channel_number]
        return None

    def index_from_channel(self, channel):
        index = 0
        for station in self.stations:
            if station["channel_number"] == channel:
                return index
            index += 1
        return None

    def get_day_parts(self):
        return self.server_conf["day_parts"]

    def load_main_config(self):
        _l = logging.getLogger("STATIONMANAGER")
        if os.path.exists(StationManager.__main_config_path):
            with open(StationManager.__main_config_path) as f:
                try:
                    to_check = ["channel_socket", "status_socket", "time_format", "start_mpv", "db_path", "server_host", "server_port"]
                    d = json.load(f)

                    for key in to_check:
                        if key in d:
                            self.server_conf[key] = d[key]

                    if "day_parts" in d:
                        new_parts = {}
                        for key in d["day_parts"]:
                            start_hour = d["day_parts"][key]["start_hour"]
                            end_hour = d["day_parts"][key]["end_hour"]
                            if end_hour > start_hour:
                                new_parts[key] = range(start_hour, end_hour)
                            else:
                                # wraps midnight - manually build the list of hours
                                hours = []
                                hour = start_hour
                                while hour <= 23:
                                    hours.append(hour)
                                    hour += 1
                                hour = 0
                                while hour <= end_hour:
                                    hours.append(hour)
                                    hour += 1
                                new_parts[key] = hours
                        self.server_conf["day_parts"] = new_parts

                    if "date_time_format" not in d:
                        # check the environment variable or set default then
                        self.server_conf["date_time_format"] = os.environ.get("FS42_TS", "%Y-%m-%dT%H:%M:%S")
                    else:
                        self.server_conf["date_time_format"] = d["date_time_format"]

                except Exception as e:
                    print(e)
                    _l.exception(e)
                    _l.error(f"Error loading main config overrides from {StationManager.__main_config_path}")
                    exit(-1)
        # else skip, no over rides

    def load_json_stations(self):
        _l = logging.getLogger("STATIONMANAGER")
        cfiles = glob.glob("confs/*.json")
        station_buffer = []
        for fname in cfiles:
            if fname != StationManager.__main_config_path:
                with open(fname) as f:
                    try:
                        d = json.load(f)
                        # set defaults for optionals
                        for key in StationManager.__overwatch:
                            if key not in d["station_conf"]:
                                d["station_conf"][key] = StationManager.__overwatch[key]

                        for to_check in StationManager.__filechecks:
                            if to_check in d["station_conf"]:
                                if not os.path.exists(d["station_conf"][to_check]):
                                    _l.error("*" * 60)
                                    _l.error(f"Error while checking configuration for {fname}")
                                    _l.error(
                                        f"The filepath specified for {to_check} does not exist: {d['station_conf'][to_check]}"
                                    )
                                    _l.error("*" * 60)
                                    exit(-1)

                        # normalize clip shows. Can be of form: ["some_show", {tag:other_show, duration:other_duration}]
                        # want to normalize them all to the tag/duration form and convert minutes to account for break strategy
                        clip_dict = {}

                        for entry in d["station_conf"]["clip_shows"]:
                            clip_tag = ""
                            requested_duration = 0
                            if isinstance(entry, str):
                                # then set to default of an hour
                                clip_tag = entry
                                requested_duration = 60
                            else:
                                # make sure it is well formed
                                if "tags" in entry:
                                    clip_tag = entry["tags"]
                                    if "duration" in entry:
                                        # then just use the entry
                                        requested_duration = entry["duration"]
                                    else:
                                        # then default the duration
                                        requested_duration = 60
                                else:
                                    _l.error("*" * 60)
                                    _l.error(f"Error while checking clip show configuration for {fname}")
                                    _l.error(f"Can't determine tag for input {entry}")
                                    _l.error("*" * 60)
                                    exit(-1)

                            fill_target = 1.0
                            # determine how much to fill with clips based on break strategy
                            # 0.73 is the calculated average for content vs breaks
                            if d["station_conf"]["schedule_increment"]:
                                fill_target = 0.95 if d["station_conf"]["schedule_increment"] else 0.73

                            # change minutes to seconds and apply keep-ratio based on break strategy
                            target_seconds = (requested_duration * timings.MIN_1) * fill_target
                            clip_dict[clip_tag] = {"tags": clip_tag, "duration": target_seconds}

                        d["station_conf"]["clip_shows"] = clip_dict

                        # add some metadata that we can use later
                        if d["station_conf"]["network_type"] in self.no_catalog:
                            d["station_conf"]["_has_catalog"] = False
                        else:
                            d["station_conf"]["_has_catalog"] = True

                        if d["station_conf"]["network_type"] in self.no_schedule:
                            d["station_conf"]["_has_schedule"] = False
                        else:
                            d["station_conf"]["_has_schedule"] = True

                        station_buffer.append(d["station_conf"])

                    except Exception as e:
                        _l.error("*" * 60)
                        _l.error(f"Error loading station configuration: {fname}")
                        _l.exception(e)
                        _l.error("*" * 60)
                        exit(-1)

        self.stations = sorted(station_buffer, key=lambda station: station["channel_number"])

        # make index
        for station in self.stations:
            self._name_index[station["network_name"]] = station
            self._number_index[station["channel_number"]] = station
