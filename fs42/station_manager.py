import logging
import os
from fs42.slot_reader import SlotReader
from fs42.station_io import StationIO

class StationManager(object):
    # the borg singleton pattern
    __we_are_all_one = {}
    _initialized = False

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
                self.station_io = StationIO()
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
                    "title_patterns": [],
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
        d = self.station_io.load_main_config()

        if d is not None:
            try:
                to_check = [
                    "channel_socket",
                    "status_socket",
                    "time_format",
                    "start_mpv",
                    "db_path",
                    "server_host",
                    "server_port",
                    "normalize_titles"
                ]

                for key in to_check:
                    if key in d:
                        self.server_conf[key] = d[key]

                # Load custom title patterns if provided
                if "title_patterns" in d:
                    import re
                    custom_patterns = []
                    for i, pattern_config in enumerate(d["title_patterns"]):
                        try:
                            # Validate that required fields exist
                            if "pattern" not in pattern_config:
                                _l.error(f"title_patterns[{i}]: missing 'pattern' field")
                                continue
                            if "group" not in pattern_config:
                                _l.error(f"title_patterns[{i}]: missing 'group' field")
                                continue

                            # Validate that the regex compiles
                            re.compile(pattern_config["pattern"])

                            # Add as tuple (pattern, group) to match existing format
                            custom_patterns.append((pattern_config["pattern"], pattern_config["group"]))

                            desc = pattern_config.get("description", f"Custom pattern {i+1}")
                            _l.info(f"Loaded custom title pattern: {desc}")
                        except re.error as e:
                            _l.error(f"Invalid regex in title_patterns[{i}]: {e}")
                            _l.error(f"Pattern was: {pattern_config.get('pattern', 'N/A')}")

                    self.server_conf["title_patterns"] = custom_patterns
                    if custom_patterns:
                        _l.info(f"Loaded {len(custom_patterns)} custom title pattern(s)")

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
                _l.error(f"Error loading main config overrides from {self.station_io.main_config_path}")
                exit(-1)
        # else: skip, no overrides (title_patterns already initialized to [] in __init__)

    def load_json_stations(self):
        """Load and index all station configurations."""
        _l = logging.getLogger("STATIONMANAGER")

        try:
            # Let StationIO do all the heavy lifting
            station_configs = self.station_io.load_and_process_all_stations()

            # Sort by channel number
            self.stations = sorted(station_configs, key=lambda station: station["channel_number"])

            # Build indexes
            self._build_indexes()

        except Exception as e:
            _l.error("*" * 60)
            _l.error("Error loading station configurations")
            _l.exception(e)
            _l.error("*" * 60)
            exit(-1)

    def _build_indexes(self):
        """Build name and channel number indexes for fast lookup."""
        self._name_index = {}
        self._number_index = {}
        for station in self.stations:
            self._name_index[station["network_name"]] = station
            self._number_index[station["channel_number"]] = station

    def write_station_config(self, network_name, config_data, is_update=False):
        """
        Write a station configuration.
        Delegates to StationIO for all the work, then reloads.
        """
        # Let StationIO handle validation, uniqueness checks, and file writing
        success, message, file_path = self.station_io.save_station_config(
            network_name, config_data, self.stations, is_update
        )

        if success:
            # Reload the station configuration
            self._reload_stations()

        return success, message, file_path

    def delete_station_config(self, network_name):
        """
        Delete a station configuration.
        Delegates to StationIO for all the work, then reloads.
        """
        # Let StationIO handle existence checks and file deletion
        success, message = self.station_io.remove_station_config(network_name, self.stations)

        if success:
            # Reload stations
            self._reload_stations()

        return success, message

    def _reload_stations(self):
        """Reload all station configurations from disk."""
        _l = logging.getLogger("STATIONMANAGER")
        _l.info("Reloading station configurations...")

        # Clear current stations and indexes
        self.stations = []
        self._name_index = {}
        self._number_index = {}

        # Reload from disk (this also rebuilds indexes)
        self.load_json_stations()

        # Re-apply tag smoothing for standard networks
        for i in range(len(self.stations)):
            station = self.stations[i]
            if station["network_type"] == "standard":
                self.stations[i] = SlotReader.smooth_tags(station)

        # Rebuild indexes after tag smoothing
        self._build_indexes()

        _l.info(f"Reloaded {len(self.stations)} station(s)")
