import logging

import pytest

from fs42.marathon_agent import MarathonAgent
from fs42.station_io import StationIO
from datetime import datetime


def _config(meta_hints, content_dir):
    return {
        "station_conf": {
            "network_name": "Test",
            "channel_number": 4,
            "network_type": "standard",
            "content_dir": str(content_dir),
            "meta_hints": meta_hints,
        }
    }


class TestMetaHintFieldValidation:
    # an unknown field is ignored at schedule time, leaving content less restricted
    # than intended, so it has to be rejected while the config is being read

    def _process(self, meta_hints, content_dir):
        # content_dir has to exist on disk - StationIO.FILE_CHECKS verifies it
        return StationIO()._process_single_config(
            _config(meta_hints, content_dir), "test_station.json"
        )

    def test_every_known_field_is_accepted(self, tmp_path):
        self._process([
            {"tags": "a", "day_part": "morning"},
            {"tags": "b", "date_range": "December 1 - December 25"},
            {"tags": "c", "week_number": 20},
            {"tags": "d", "custom_holiday": "thanksgiving"},
            {"tags": "e", "custom_holiday": "thanksgiving", "exclusive": True},
            {"tags": "f", "month": "October"},
            {"tags": "g", "quarter": "Q4"},
            {"tags": "h", "day_of_week": "friday"},
        ], tmp_path)

    def test_unknown_field_is_rejected(self, tmp_path):
        with pytest.raises(Exception) as err:
            self._process([{"tags": "a", "holiday": "thanksgiving"}], tmp_path)
        message = str(err.value)
        assert "holiday" in message
        assert "test_station.json" in message
        # the message should name what was expected instead
        assert "custom_holiday" in message

    def test_missing_tags_is_still_rejected(self, tmp_path):
        with pytest.raises(Exception, match="No meta_hints tag specified"):
            self._process([{"day_part": "morning"}], tmp_path)

    def test_several_unknown_fields_are_all_reported(self, tmp_path):
        with pytest.raises(Exception) as err:
            self._process([{"tags": "a", "holiday": "x", "week": 20}], tmp_path)
        message = str(err.value)
        assert "holiday" in message
        assert "week" in message


class TestMarathonHintWarning:
    def test_unmatched_hint_warns_and_leaves_marathon_unrestricted(self, caplog):
        slot = {"marathon": {"count": 4, "chance": 1.0, "hint": "thanksigving"}}
        with caplog.at_level(logging.WARNING):
            assert MarathonAgent.detect_marathon(slot, datetime(2026, 3, 1, 12))
        assert "thanksigving" in caplog.text
        assert "unrestricted" in caplog.text

    def test_matched_hint_does_not_warn(self, caplog):
        slot = {"marathon": {"count": 4, "chance": 1.0, "hint": "October"}}
        with caplog.at_level(logging.WARNING):
            assert MarathonAgent.detect_marathon(slot, datetime(2026, 10, 1, 12))
            assert not MarathonAgent.detect_marathon(slot, datetime(2026, 3, 1, 12))
        assert caplog.text == ""