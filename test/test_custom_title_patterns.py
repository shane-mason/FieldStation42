import pytest
from unittest.mock import patch
from fs42.station_manager import StationManager
from fs42.station_io import StationIO


class TestCustomTitlePatternsLoading:
    """Integration tests for loading custom title patterns from main_config.json"""

    def setup_method(self):
        """Reset StationManager singleton before each test"""
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

    def _make_manager(self, config_data):
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.station_io.glob.glob', return_value=[]):
                return StationManager()

    def test_load_valid_custom_patterns(self):
        """Test loading valid custom patterns from main_config.json"""
        config_data = {
            "server_port": 4242,
            "title_patterns": [
                {
                    "pattern": r"^\[Studio\][\s._-]+(.+?)[\s._-]+Special.*$",
                    "group": 1,
                    "description": "Studio specials"
                },
                {
                    "pattern": r"^(.+?)[\s._-]+HD[\s._-]+\d+p.*$",
                    "group": 1,
                    "description": "HD quality markers"
                }
            ]
        }

        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 2

        first_pattern = manager.server_conf["title_patterns"][0]
        assert first_pattern[0] == r"^\[Studio\][\s._-]+(.+?)[\s._-]+Special.*$"
        assert first_pattern[1] == 1

        second_pattern = manager.server_conf["title_patterns"][1]
        assert second_pattern[0] == r"^(.+?)[\s._-]+HD[\s._-]+\d+p.*$"
        assert second_pattern[1] == 1

    def test_load_empty_custom_patterns(self):
        """Test loading empty custom patterns array"""
        manager = self._make_manager({"server_port": 4242, "title_patterns": []})

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 0

    def test_no_custom_patterns_in_config(self):
        """Test when title_patterns key is not in config"""
        manager = self._make_manager({"server_port": 4242})

        assert "title_patterns" in manager.server_conf
        assert manager.server_conf["title_patterns"] == []

    def test_no_main_config_file(self):
        """Test when main_config.json doesn't exist"""
        manager = self._make_manager(None)

        assert "title_patterns" in manager.server_conf
        assert manager.server_conf["title_patterns"] == []

    def test_pattern_missing_pattern_field(self):
        """Test handling of pattern missing 'pattern' field"""
        config_data = {
            "title_patterns": [
                {"group": 1, "description": "Invalid - missing pattern field"}
            ]
        }
        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 0

    def test_pattern_missing_group_field(self):
        """Test handling of pattern missing 'group' field"""
        config_data = {
            "title_patterns": [
                {"pattern": r"^(.+?)$", "description": "Invalid - missing group field"}
            ]
        }
        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 0

    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex pattern"""
        config_data = {
            "title_patterns": [
                {"pattern": r"^([abc", "group": 1, "description": "Invalid regex"}
            ]
        }
        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 0

    def test_mixed_valid_and_invalid_patterns(self):
        """Test that valid patterns are loaded even when some are invalid"""
        config_data = {
            "title_patterns": [
                {"pattern": r"^(.+?)[\s._-]+Valid.*$", "group": 1, "description": "Valid pattern 1"},
                {"pattern": r"^([abc", "group": 1, "description": "Invalid regex"},
                {"group": 1, "description": "Missing pattern"},
                {"pattern": r"^Another(.+?)Valid.*$", "group": 1, "description": "Valid pattern 2"},
            ]
        }
        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 2

        patterns = manager.server_conf["title_patterns"]
        assert patterns[0][0] == r"^(.+?)[\s._-]+Valid.*$"
        assert patterns[1][0] == r"^Another(.+?)Valid.*$"

    def test_pattern_with_different_group_number(self):
        """Test pattern with capture group other than 1"""
        config_data = {
            "title_patterns": [
                {
                    "pattern": r"^(.+?)[\s._-]+(.+?)[\s._-]+\d+$",
                    "group": 2,
                    "description": "Second group pattern"
                }
            ]
        }
        manager = self._make_manager(config_data)

        assert "title_patterns" in manager.server_conf
        assert len(manager.server_conf["title_patterns"]) == 1

        pattern = manager.server_conf["title_patterns"][0]
        assert pattern[1] == 2