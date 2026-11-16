import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())

from fs42.config_processor import ConfigProcessor, ConfigurationError  # noqa: E402
from fs42.slot_reader import SlotReader  # noqa: E402


class TestDateKeyMatches:
    def test_single_day(self):
        assert SlotReader._date_key_matches("April 23", datetime(2026, 4, 23, 20, 0))
        assert not SlotReader._date_key_matches("April 23", datetime(2026, 4, 24, 20, 0))

    def test_same_year_range(self):
        assert SlotReader._date_key_matches("April 23 - April 25", datetime(2026, 4, 24))
        assert not SlotReader._date_key_matches("April 23 - April 25", datetime(2026, 4, 26))

    def test_wraparound_range(self):
        key = "December 24 - January 2"
        assert SlotReader._date_key_matches(key, datetime(2026, 12, 30))
        assert SlotReader._date_key_matches(key, datetime(2027, 1, 1))
        assert not SlotReader._date_key_matches(key, datetime(2027, 1, 3))

    def test_leap_day_uses_scheduled_year(self):
        assert SlotReader._date_key_matches("February 29", datetime(2028, 2, 29))
        assert not SlotReader._date_key_matches("February 29", datetime(2027, 3, 1))


class TestValidDateKey:
    def test_valid_keys(self):
        assert ConfigProcessor._valid_date_key("April 23")
        assert ConfigProcessor._valid_date_key("December 24 - January 2")

    def test_invalid_day_rejected(self):
        with pytest.raises(ConfigurationError):
            ConfigProcessor._valid_date_key("April 31")
