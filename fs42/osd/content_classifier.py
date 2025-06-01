import json
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from fs42.station_manager import StationManager
except ImportError:
    raise ImportError("Failed to import StationManager from fs42.station_manager. "
                     "Please ensure the 'fs42' library is installed and in your PYTHONPATH.")


class ContentType:
    FEATURE = "FEATURE"
    COMMERCIAL = "COMMERCIAL"
    BUMPER = "BUMPER"
    UNKNOWN = "UNKNOWN"


class ContentClassifier:    
    def __init__(self, socket_file: str = "runtime/play_status.socket"):
        self.socket_file = Path(socket_file)
        self.station_manager = StationManager()
        self._cached_network = None
        self._content_dir_pattern = None
        self._commercial_dir_pattern = None
        self._bump_dir_pattern = None

    def _is_relative_to(self, path: Path, base_path: Path) -> bool:
        if not path or not base_path:
            return False
        try:
            path.relative_to(base_path)
            return True
        except (ValueError, TypeError):
            return False

    def _load_station_config(self, network_name: str) -> Optional[Dict[str, Any]]:
        if not network_name:
            self._content_dir_pattern = None
            self._commercial_dir_pattern = None
            self._bump_dir_pattern = None
            return None
        
        try:
            config = self.station_manager.station_by_name(network_name)
            if not config:
                self._content_dir_pattern = None
                self._commercial_dir_pattern = None
                self._bump_dir_pattern = None
                return None
            
            content_dir_config_val = config.get('content_dir')
            if not content_dir_config_val:
                self._content_dir_pattern = None
                self._commercial_dir_pattern = None
                self._bump_dir_pattern = None
                return config

            self._content_dir_pattern = Path(content_dir_config_val)
            commercial_subdir_str = config.get('commercial_dir', 'commercials')
            self._commercial_dir_pattern = self._content_dir_pattern / Path(commercial_subdir_str)
            bump_subdir_str = config.get('bump_dir', 'bumps')
            self._bump_dir_pattern = self._content_dir_pattern / Path(bump_subdir_str)

            return config
        except Exception:
            self._content_dir_pattern = None
            self._commercial_dir_pattern = None
            self._bump_dir_pattern = None
            return None

    def _read_socket_status(self) -> Optional[Dict[str, Any]]:
        try:
            with self.socket_file.open("r") as f:
                content = f.read().strip()
                if not content:
                    return None
                return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            return None

    def classify_from_socket(self) -> str:
        status_data = self._read_socket_status()
        if not status_data:
            return ContentType.UNKNOWN

        network_name = status_data.get("network_name")
        file_path = status_data.get("file_path")
        title = status_data.get("title")

        return self.classify_content(title, file_path, network_name)

    def classify_content(self, title: Optional[str], file_path: Optional[str], 
                        network_name: Optional[str]) -> str:
        if not file_path or not title or not network_name:
            return ContentType.UNKNOWN

        if network_name != self._cached_network:
            self._load_station_config(network_name)
            self._cached_network = network_name

        if not self._content_dir_pattern:
            return ContentType.UNKNOWN

        try:
            playing_file_path_obj = Path(file_path)

            if (self._commercial_dir_pattern and 
                self._is_relative_to(playing_file_path_obj, self._commercial_dir_pattern)):
                return ContentType.COMMERCIAL
            elif (self._bump_dir_pattern and 
                  self._is_relative_to(playing_file_path_obj, self._bump_dir_pattern)):
                return ContentType.BUMPER
            elif self._is_relative_to(playing_file_path_obj, self._content_dir_pattern):
                return ContentType.FEATURE
            else:
                return ContentType.UNKNOWN
        except Exception:
            return ContentType.UNKNOWN

def classify_current_content(socket_file: str = "runtime/play_status.socket") -> str:
    classifier = ContentClassifier(socket_file)
    return classifier.classify_from_socket()

