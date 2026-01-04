import json
import logging
import os
import glob
import re
import shutil
from fs42.config_processor import ConfigProcessor
from fs42 import timings


class StationIO:
    """
    StationIO handles all file I/O operations for station configurations.
    This includes reading, writing, and deleting station configuration files.
    """

    # Defaults for optional station config fields
    OVERWATCH_DEFAULTS = {
        "network_type": "standard",
        "schedule_increment": 30,
        "break_strategy": "standard",
        "commercial_free": False,
        "clip_shows": [],
        "break_duration": 120,
        "hidden": False,
        "media_filter": "video",
    }

    # Fields that reference files that should exist
    FILE_CHECKS = ["sign_off_video", "off_air_video", "standby_image", "be_right_back_media"]

    # Network types that don't have catalogs or schedules
    NO_CATALOG = {"guide", "streaming", "web"}
    NO_SCHEDULE = {"guide", "streaming", "web"}
    

    def __init__(self):
        self._l = logging.getLogger("STATIONIO")
        self.confs_dir = "confs/"
        self.main_config_path = "confs/main_config.json"
        self.schema_path = "fs42/station_config_schema.json"

    def load_schema(self):
        if os.path.exists(self.schema_path):
            with open(self.schema_path) as f:
                return json.load(f)
        return None

    def normalize_filename(self, network_name):
        # Convert to lowercase, replace spaces and special chars with underscores
        safe_name = re.sub(r'[^\w\s-]', '', network_name.lower())
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        return safe_name.strip('_')

    def get_config_file_path(self, network_name):
        filename = self.normalize_filename(network_name)
        return f"{self.confs_dir}{filename}.json"

    def load_main_config(self):

        if os.path.exists(self.main_config_path):
            try:
                with open(self.main_config_path) as f:
                    return json.load(f)
            except Exception as e:
                self._l.error(f"Error loading main config from {self.main_config_path}")
                self._l.exception(e)
                raise
        return None

    def load_all_station_configs(self):

        cfiles = glob.glob(f"{self.confs_dir}*.json")
        station_configs = []

        for fname in cfiles:
            # Skip the main config file
            if os.path.normpath(fname) != os.path.normpath(self.main_config_path):
                try:
                    with open(fname) as f:
                        d = json.load(f)
                        station_configs.append({
                            'config': d,
                            'filename': fname
                        })
                except Exception as e:
                    self._l.error(f"Error loading station configuration: {fname}")
                    self._l.exception(e)
                    raise

        return station_configs

    def read_raw_station_config(self, network_name):
        """
        Read a station configuration file without any processing or normalization.
        Returns the raw JSON data exactly as it appears on disk.

        Args:
            network_name: The network name to look up

        Returns:
            tuple: (success: bool, data: dict or None, error_message: str or None)
        """
        file_path = self.find_config_by_network_name(network_name)

        if file_path is None:
            return False, None, f"Station '{network_name}' not found"

        try:
            with open(file_path) as f:
                raw_data = json.load(f)
            return True, raw_data, None
        except Exception as e:
            self._l.error(f"Error reading configuration file: {file_path}")
            self._l.exception(e)
            return False, None, f"Failed to read configuration: {str(e)}"

    def list_raw_station_configs(self):
        """
        List all station configurations without processing or normalization.
        Returns raw JSON data exactly as it appears on disk.

        Returns:
            list: List of raw station configuration dictionaries
        """
        cfiles = glob.glob(f"{self.confs_dir}*.json")
        raw_configs = []

        for fname in cfiles:
            # Skip the main config file
            if os.path.normpath(fname) != os.path.normpath(self.main_config_path):
                try:
                    with open(fname) as f:
                        raw_data = json.load(f)
                        raw_configs.append(raw_data)
                except Exception as e:
                    self._l.error(f"Error loading station configuration: {fname}")
                    self._l.exception(e)
                    # Continue loading other stations even if one fails
                    continue

        return raw_configs

    def write_station_config(self, file_path, config_data):

        # Create backup if file exists
        if os.path.exists(file_path):
            backup_path = f"{file_path}.bak"
            try:
                shutil.copy2(file_path, backup_path)
                self._l.info(f"Created backup: {backup_path}")
            except Exception as e:
                self._l.error(f"Failed to create backup: {e}")
                return False, f"Failed to create backup: {str(e)}"

        # Write to temporary file first (atomic write)
        temp_path = f"{file_path}.tmp"
        try:
            with open(temp_path, 'w') as f:
                json.dump(config_data, f, indent=2)

            # Rename temp file to actual file (atomic on POSIX systems)
            os.rename(temp_path, file_path)
            self._l.info(f"Successfully wrote configuration to {file_path}")

            return True, "Configuration file written successfully"

        except Exception as e:
            self._l.error(f"Failed to write configuration: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as cleanup_error:
                    self._l.warning(f"Failed to clean up temp file {temp_path}: {cleanup_error}")
            return False, f"Failed to write configuration: {str(e)}"

    def delete_station_file(self, file_path):

        if not os.path.exists(file_path):
            return False, f"Configuration file not found: {file_path}"

        # Create backup before deletion
        backup_path = f"{file_path}.bak"
        try:
            shutil.copy2(file_path, backup_path)
            self._l.info(f"Created backup before deletion: {backup_path}")
        except Exception as e:
            self._l.warning(f"Failed to create backup: {e}")

        # Delete the file
        try:
            os.remove(file_path)
            self._l.info(f"Deleted configuration file: {file_path}")
            return True, "Configuration file deleted successfully"
        except Exception as e:
            self._l.error(f"Failed to delete configuration: {e}")
            return False, f"Failed to delete configuration: {str(e)}"

    def find_config_by_network_name(self, network_name):

        for conf_file in glob.glob(f"{self.confs_dir}*.json"):
            if os.path.normpath(conf_file) != os.path.normpath(self.main_config_path):
                try:
                    with open(conf_file) as f:
                        d = json.load(f)
                        if d.get("station_conf", {}).get("network_name") == network_name:
                            self._l.info(f"Found configuration for '{network_name}' in: {conf_file}")
                            return conf_file
                except (OSError, json.JSONDecodeError, KeyError) as e:
                    # Skip files that can't be read, parsed, or don't have expected structure
                    self._l.debug(f"Skipping {conf_file} during search: {e}")
                    continue
        return None

    def _process_single_config(self, config_data, filename):

        # Preprocess the configuration
        config_data["station_conf"] = ConfigProcessor.preprocess(config_data["station_conf"])

        station_conf = config_data["station_conf"]

        # Apply defaults for optional fields
        for key in StationIO.OVERWATCH_DEFAULTS:
            if key not in station_conf:
                station_conf[key] = StationIO.OVERWATCH_DEFAULTS[key]

        # Check that referenced files exist
        for to_check in StationIO.FILE_CHECKS:
            if to_check in station_conf:
                if not os.path.exists(station_conf[to_check]):
                    self._l.error("*" * 60)
                    self._l.error(f"Error while checking configuration for {filename}")
                    self._l.error(
                        f"The filepath specified for {to_check} does not exist: {station_conf[to_check]}"
                    )
                    self._l.error("*" * 60)
                    raise FileNotFoundError(f"Missing file: {station_conf[to_check]}")

        # Normalize clip shows
        station_conf["clip_shows"] = self._normalize_clip_shows(station_conf["clip_shows"],
                                                                  station_conf["schedule_increment"],
                                                                  filename)

        # Add metadata flags
        station_conf["_has_catalog"] = station_conf["network_type"] not in StationIO.NO_CATALOG
        station_conf["_has_schedule"] = station_conf["network_type"] not in StationIO.NO_SCHEDULE

        return station_conf

    def _normalize_clip_shows(self, clip_shows, schedule_increment, filename):

        clip_dict = {}

        for entry in clip_shows:
            clip_tag = ""
            requested_duration = 0

            if isinstance(entry, str):
                # Simple string form - default to 1 hour
                clip_tag = entry
                requested_duration = 60
            else:
                # Dictionary form - extract tags and duration
                if "tags" in entry:
                    clip_tag = entry["tags"]
                    requested_duration = entry.get("duration", 60)
                else:
                    self._l.error("*" * 60)
                    self._l.error(f"Error while checking clip show configuration for {filename}")
                    self._l.error(f"Can't determine tag for input {entry}")
                    self._l.error("*" * 60)
                    raise ValueError(f"Invalid clip show entry: {entry}")

            # Determine fill target based on break strategy
            # go a little below if there will be commercials
            fill_target = 0.95 if schedule_increment else 1.0

            # Convert minutes to seconds and apply fill ratio
            target_seconds = (requested_duration * timings.MIN_1) * fill_target
            clip_dict[clip_tag] = {"tags": clip_tag, "duration": target_seconds}

        return clip_dict

    def load_and_process_all_stations(self):

        raw_configs = self.load_all_station_configs()
        processed_stations = []

        for config_data in raw_configs:
            fname = config_data['filename']
            config = config_data['config']

            try:
                processed_conf = self._process_single_config(config, fname)
                processed_stations.append(processed_conf)
            except Exception as e:
                self._l.error("*" * 60)
                self._l.error(f"Error loading station configuration: {fname}")
                self._l.exception(e)
                self._l.error("*" * 60)
                raise

        return processed_stations

    def validate_station_config(self, config_data):

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
        try:
            import jsonschema
            schema = self.load_schema()
            if schema:
                try:
                    jsonschema.validate(config_data, schema)
                except jsonschema.ValidationError as e:
                    errors.append(f"Schema validation error: {e.message}")
                except Exception as e:
                    self._l.error(f"Error during schema validation: {e}")
                    errors.append(f"Schema validation error: {str(e)}")
            else:
                self._l.warning("Could not load station_config_schema.json for validation")
        except ImportError:
            # jsonschema not installed - return error with installation instructions
            error_msg = (
                "The 'jsonschema' library is required for station configuration validation. "
                "Please install it by running the installer or: pip install jsonschema"
            )
            self._l.error(error_msg)
            errors.append(error_msg)

        # Warn about missing files (don't fail, just warn)
        for to_check in StationIO.FILE_CHECKS:
            if to_check in station_conf:
                if not os.path.exists(station_conf[to_check]):
                    warning = f"File not found: {station_conf[to_check]} (referenced in '{to_check}')"
                    self._l.warning(warning)
                    # Don't add to errors, just log warning

        if errors:
            return False, errors
        return True, []

    def save_station_config(self, network_name, config_data, existing_stations, is_update=False):

        # Validate the configuration
        is_valid, errors = self.validate_station_config(config_data)
        if not is_valid:
            error_msg = "; ".join(errors)
            self._l.error(f"Validation failed for station '{network_name}': {error_msg}")
            return False, f"Validation failed: {error_msg}", None

        station_conf = config_data["station_conf"]

        # Check uniqueness
        exclude_name = network_name if is_update else None
        is_unique, uniqueness_error = self._check_uniqueness(
            station_conf["channel_number"],
            station_conf["network_name"],
            existing_stations,
            exclude_name=exclude_name
        )
        if not is_unique:
            return False, uniqueness_error, None

        # Get file path
        file_path = self.get_config_file_path(network_name)

        # For updates, check if we're renaming
        old_file_path = None
        if is_update and network_name != station_conf["network_name"]:
            old_file_path = self.get_config_file_path(network_name)
            file_path = self.get_config_file_path(station_conf["network_name"])

        # Write the configuration
        success, message = self.write_station_config(file_path, config_data)

        if not success:
            return False, message, None

        # If this was a rename, delete the old file
        if old_file_path and old_file_path != file_path and os.path.exists(old_file_path):
            os.remove(old_file_path)
            self._l.info(f"Removed old configuration file: {old_file_path}")

        return True, "Station configuration saved successfully", file_path

    def remove_station_config(self, network_name, existing_stations):

        # Check if station exists
        station_exists = any(s["network_name"] == network_name for s in existing_stations)
        if not station_exists:
            msg = f"Station '{network_name}' not found"
            self._l.warning(msg)
            return False, msg

        # Get file path
        file_path = self.get_config_file_path(network_name)

        if not os.path.exists(file_path):
            # Station exists in memory but file not found - try to find it
            # This could happen if the file was manually renamed
            self._l.warning(f"Expected file not found: {file_path}")
            file_path = self.find_config_by_network_name(network_name)

            if file_path is None:
                msg = f"Configuration file for '{network_name}' not found"
                self._l.error(msg)
                return False, msg

        # Delete the file
        success, message = self.delete_station_file(file_path)

        if not success:
            return False, message

        return True, f"Station '{network_name}' deleted successfully"

    def _check_uniqueness(self, channel_number, network_name, existing_stations, exclude_name=None):

        # Check channel number uniqueness
        for station in existing_stations:
            if exclude_name and station["network_name"] == exclude_name:
                continue
            if station["channel_number"] == channel_number:
                msg = f"Channel number {channel_number} is already used by station '{station['network_name']}'"
                self._l.warning(msg)
                return False, msg

        # Check network name uniqueness
        for station in existing_stations:
            if exclude_name and station["network_name"] == exclude_name:
                continue
            if station["network_name"] == network_name:
                msg = f"Network name '{network_name}' already exists"
                self._l.warning(msg)
                return False, msg

        return True, None
