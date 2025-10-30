import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from fs42.station_manager import StationManager


class TestCustomTitlePatternsLoading:
    """Integration tests for loading custom title patterns from main_config.json"""

    def setup_method(self):
        """Reset StationManager singleton before each test"""
        # Clear the singleton state
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

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

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            # Patch the main config path
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                # Mock glob to return no station configs
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    manager = StationManager()

                    # Verify patterns were loaded
                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 2

                    # Verify pattern structure
                    first_pattern = manager.server_conf["title_patterns"][0]
                    assert first_pattern[0] == r"^\[Studio\][\s._-]+(.+?)[\s._-]+Special.*$"
                    assert first_pattern[1] == 1

                    second_pattern = manager.server_conf["title_patterns"][1]
                    assert second_pattern[0] == r"^(.+?)[\s._-]+HD[\s._-]+\d+p.*$"
                    assert second_pattern[1] == 1

        finally:
            os.unlink(temp_config_path)

    def test_load_empty_custom_patterns(self):
        """Test loading empty custom patterns array"""
        config_data = {
            "server_port": 4242,
            "title_patterns": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    manager = StationManager()

                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 0

        finally:
            os.unlink(temp_config_path)

    def test_no_custom_patterns_in_config(self):
        """Test when title_patterns key is not in config"""
        config_data = {
            "server_port": 4242
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    manager = StationManager()

                    # Should have empty list when not specified
                    assert "title_patterns" in manager.server_conf
                    assert manager.server_conf["title_patterns"] == []

        finally:
            os.unlink(temp_config_path)

    def test_no_main_config_file(self):
        """Test when main_config.json doesn't exist"""
        with patch.object(StationManager, '_StationManager__main_config_path', '/nonexistent/path.json'):
            with patch('fs42.station_manager.glob.glob', return_value=[]):
                manager = StationManager()

                # Should have empty list when no config file
                assert "title_patterns" in manager.server_conf
                assert manager.server_conf["title_patterns"] == []

    def test_pattern_missing_pattern_field(self):
        """Test handling of pattern missing 'pattern' field"""
        config_data = {
            "title_patterns": [
                {
                    "group": 1,
                    "description": "Invalid - missing pattern field"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    # Should not crash, but pattern should be skipped
                    manager = StationManager()

                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 0

        finally:
            os.unlink(temp_config_path)

    def test_pattern_missing_group_field(self):
        """Test handling of pattern missing 'group' field"""
        config_data = {
            "title_patterns": [
                {
                    "pattern": r"^(.+?)$",
                    "description": "Invalid - missing group field"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    # Should not crash, but pattern should be skipped
                    manager = StationManager()

                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 0

        finally:
            os.unlink(temp_config_path)

    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex pattern"""
        config_data = {
            "title_patterns": [
                {
                    "pattern": r"^([abc",  # Invalid regex - unclosed bracket
                    "group": 1,
                    "description": "Invalid regex"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    # Should not crash, but invalid pattern should be skipped
                    manager = StationManager()

                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 0

        finally:
            os.unlink(temp_config_path)

    def test_mixed_valid_and_invalid_patterns(self):
        """Test that valid patterns are loaded even when some are invalid"""
        config_data = {
            "title_patterns": [
                {
                    "pattern": r"^(.+?)[\s._-]+Valid.*$",
                    "group": 1,
                    "description": "Valid pattern 1"
                },
                {
                    "pattern": r"^([abc",  # Invalid regex
                    "group": 1,
                    "description": "Invalid regex"
                },
                {
                    "group": 1,  # Missing pattern field
                    "description": "Missing pattern"
                },
                {
                    "pattern": r"^Another(.+?)Valid.*$",
                    "group": 1,
                    "description": "Valid pattern 2"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    manager = StationManager()

                    # Only the two valid patterns should be loaded
                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 2

                    # Verify the valid patterns are present
                    patterns = manager.server_conf["title_patterns"]
                    assert patterns[0][0] == r"^(.+?)[\s._-]+Valid.*$"
                    assert patterns[1][0] == r"^Another(.+?)Valid.*$"

        finally:
            os.unlink(temp_config_path)

    def test_pattern_with_different_group_number(self):
        """Test pattern with capture group other than 1"""
        config_data = {
            "title_patterns": [
                {
                    "pattern": r"^(.+?)[\s._-]+(.+?)[\s._-]+\d+$",
                    "group": 2,  # Using second capture group
                    "description": "Second group pattern"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_config_path = f.name

        try:
            with patch.object(StationManager, '_StationManager__main_config_path', temp_config_path):
                with patch('fs42.station_manager.glob.glob', return_value=[]):
                    manager = StationManager()

                    assert "title_patterns" in manager.server_conf
                    assert len(manager.server_conf["title_patterns"]) == 1

                    # Verify group number is preserved
                    pattern = manager.server_conf["title_patterns"][0]
                    assert pattern[1] == 2

        finally:
            os.unlink(temp_config_path)
