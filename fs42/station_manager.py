import json
import logging
import os
import glob
import re
import shutil
from pathlib import Path
from fs42.slot_reader import SlotReader
from fs42 import timings
from fs42.config_processor import ConfigProcessor
try:
    import jsonschema
except ImportError:
    jsonschema = None

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
        "hidden": False,
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
        if os.path.exists(StationManager.__main_config_path):
            with open(StationManager.__main_config_path) as f:
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
                    d = json.load(f)

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
                    _l.error(f"Error loading main config overrides from {StationManager.__main_config_path}")
                    exit(-1)
        # else: skip, no overrides (title_patterns already initialized to [] in __init__)

    def load_json_stations(self):
        _l = logging.getLogger("STATIONMANAGER")
        cfiles = glob.glob("confs/*.json")
        station_buffer = []
        for fname in cfiles:
            if os.path.normpath(fname) != os.path.normpath(StationManager.__main_config_path):
                with open(fname) as f:
                    try:
                        d = json.load(f)
                        d["station_conf"] = ConfigProcessor.preprocess(d["station_conf"])
                        
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

    def _load_schema(self):
        """Load the station configuration JSON schema."""
        schema_path = "fs42/station_config_schema.json"
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                return json.load(f)
        return None

    def _normalize_filename(self, network_name):
        # Convert to lowercase, replace spaces and special chars with underscores
        safe_name = re.sub(r'[^\w\s-]', '', network_name.lower())
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        return safe_name.strip('_')

    def _get_config_file_path(self, network_name):
        """Get the file path for a station configuration."""
        filename = self._normalize_filename(network_name)
        return f"confs/{filename}.json"

    def check_uniqueness(self, channel_number, network_name, exclude_name=None):
        _l = logging.getLogger("STATIONMANAGER")

        # Check channel number uniqueness
        for station in self.stations:
            if exclude_name and station["network_name"] == exclude_name:
                continue
            if station["channel_number"] == channel_number:
                msg = f"Channel number {channel_number} is already used by station '{station['network_name']}'"
                _l.warning(msg)
                return False, msg

        # Check network name uniqueness
        for station in self.stations:
            if exclude_name and station["network_name"] == exclude_name:
                continue
            if station["network_name"] == network_name:
                msg = f"Network name '{network_name}' already exists"
                _l.warning(msg)
                return False, msg

        return True, None

    def validate_station_config(self, config_data):

        _l = logging.getLogger("STATIONMANAGER")
        errors = []

        # Check that station_conf wrapper exists
        if "station_conf" not in config_data:
            errors.append("Configuration must have a 'station_conf' top-level key")
            return False, errors

        station_conf = config_data["station_conf"]

        # Check required fields
        if "network_name" not in station_conf:
            errors.append("'network_name' is required")
        if "channel_number" not in station_conf:
            errors.append("'channel_number' is required")

        # Validate with JSON schema if available
        if jsonschema is not None:
            schema = self._load_schema()
            if schema:
                try:
                    jsonschema.validate(config_data, schema)
                except jsonschema.ValidationError as e:
                    errors.append(f"Schema validation error: {e.message}")
                except Exception as e:
                    _l.error(f"Error during schema validation: {e}")
                    errors.append(f"Schema validation error: {str(e)}")
            else:
                _l.warning("Could not load station_config_schema.json for validation")
        else:
            # jsonschema not installed - return error with installation instructions
            error_msg = (
                "The 'jsonschema' library is required for station configuration validation. "
                "Please install it by running the installer or: pip install jsonschema"
            )
            _l.error(error_msg)
            errors.append(error_msg)

        # Warn about missing files (don't fail, just warn)
        for to_check in self.__filechecks:
            if to_check in station_conf:
                if not os.path.exists(station_conf[to_check]):
                    warning = f"File not found: {station_conf[to_check]} (referenced in '{to_check}')"
                    _l.warning(warning)
                    # Don't add to errors, just log warning

        if errors:
            return False, errors
        return True, []

    def write_station_config(self, network_name, config_data, is_update=False):

        _l = logging.getLogger("STATIONMANAGER")

        # Validate the configuration
        is_valid, errors = self.validate_station_config(config_data)
        if not is_valid:
            error_msg = "; ".join(errors)
            _l.error(f"Validation failed for station '{network_name}': {error_msg}")
            return False, f"Validation failed: {error_msg}", None

        station_conf = config_data["station_conf"]

        # Check uniqueness
        exclude_name = network_name if is_update else None
        is_unique, uniqueness_error = self.check_uniqueness(
            station_conf["channel_number"],
            station_conf["network_name"],
            exclude_name=exclude_name
        )
        if not is_unique:
            return False, uniqueness_error, None

        # Get file path
        file_path = self._get_config_file_path(network_name)

        # For updates, check if we're renaming
        old_file_path = None
        if is_update and network_name != station_conf["network_name"]:
            old_file_path = self._get_config_file_path(network_name)
            file_path = self._get_config_file_path(station_conf["network_name"])

        # Create backup if file exists
        if os.path.exists(file_path):
            backup_path = f"{file_path}.bak"
            try:
                shutil.copy2(file_path, backup_path)
                _l.info(f"Created backup: {backup_path}")
            except Exception as e:
                _l.error(f"Failed to create backup: {e}")
                return False, f"Failed to create backup: {str(e)}", None

        # Write to temporary file first (atomic write)
        temp_path = f"{file_path}.tmp"
        try:
            with open(temp_path, 'w') as f:
                json.dump(config_data, f, indent=2)

            # Rename temp file to actual file (atomic on POSIX systems)
            os.rename(temp_path, file_path)
            _l.info(f"Successfully wrote configuration to {file_path}")

            # If this was a rename, delete the old file
            if old_file_path and old_file_path != file_path and os.path.exists(old_file_path):
                os.remove(old_file_path)
                _l.info(f"Removed old configuration file: {old_file_path}")

            # Reload the station configuration
            self._reload_stations()

            return True, "Station configuration saved successfully", file_path

        except Exception as e:
            _l.error(f"Failed to write configuration: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return False, f"Failed to write configuration: {str(e)}", None

    def delete_station_config(self, network_name):
        _l = logging.getLogger("STATIONMANAGER")

        # Check if station exists
        if network_name not in self._name_index:
            msg = f"Station '{network_name}' not found"
            _l.warning(msg)
            return False, msg

        # Get file path
        file_path = self._get_config_file_path(network_name)

        if not os.path.exists(file_path):
            # Station exists in memory but file not found - try to find it
            # This could happen if the file was manually renamed
            _l.warning(f"Expected file not found: {file_path}")

            # Search for a file that contains this network_name
            for conf_file in glob.glob("confs/*.json"):
                if os.path.normpath(conf_file) != os.path.normpath(self.__main_config_path):
                    try:
                        with open(conf_file) as f:
                            d = json.load(f)
                            if d.get("station_conf", {}).get("network_name") == network_name:
                                file_path = conf_file
                                _l.info(f"Found configuration in: {file_path}")
                                break
                    except:
                        continue

            if not os.path.exists(file_path):
                msg = f"Configuration file for '{network_name}' not found"
                _l.error(msg)
                return False, msg

        # Create backup before deletion
        backup_path = f"{file_path}.bak"
        try:
            shutil.copy2(file_path, backup_path)
            _l.info(f"Created backup before deletion: {backup_path}")
        except Exception as e:
            _l.warning(f"Failed to create backup: {e}")

        # Delete the file
        try:
            os.remove(file_path)
            _l.info(f"Deleted configuration file: {file_path}")

            # Reload stations
            self._reload_stations()

            return True, f"Station '{network_name}' deleted successfully"

        except Exception as e:
            _l.error(f"Failed to delete configuration: {e}")
            return False, f"Failed to delete configuration: {str(e)}"

    def _reload_stations(self):
        """Reload all station configurations from disk."""
        _l = logging.getLogger("STATIONMANAGER")
        _l.info("Reloading station configurations...")

        # Clear current stations
        self.stations = []
        self._name_index = {}
        self._number_index = {}

        # Reload from disk
        self.load_json_stations()

        # Re-apply tag smoothing for standard networks
        for i in range(len(self.stations)):
            station = self.stations[i]
            if station["network_type"] == "standard":
                self.stations[i] = SlotReader.smooth_tags(station)

        # Rebuild indexes
        for station in self.stations:
            self._name_index[station["network_name"]] = station
            self._number_index[station["channel_number"]] = station

        _l.info(f"Reloaded {len(self.stations)} station(s)")
