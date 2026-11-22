from unittest.mock import patch
from datetime import datetime

import pytest

from fs42.catalog_entry import CatalogEntry
from fs42.hint_agent import HintAgent
from fs42.station_io import StationIO
from fs42.station_manager import StationManager

# station_io normalizes meta_hint tags into content_dir relative paths before
# HintAgent ever sees them, so these are written in the post-normalized form
CONTENT_DIR = "catalog/test"
SPECIAL = f"{CONTENT_DIR}/mix/special"
GENERAL = f"{CONTENT_DIR}/mix/general"

BOTH = ["mix/general", "mix/special"]
GENERAL_ONLY = ["mix/general"]
SPECIAL_ONLY = ["mix/special"]


class TestHintAgent:
    def setup_method(self):
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        self._make_manager({"aug_day": "August 29", "thanksgiving": "4th thursday november"})

    def _make_manager(self, custom_holidays):
        config_data = {"server_port": 4242, "custom_holidays": custom_holidays}
        with patch.object(StationIO, "load_main_config", return_value=config_data):
            with patch("fs42.station_io.glob.glob", return_value=[]):
                return StationManager()

    def _filter(self, meta_hints, when):
        # entries are rebuilt every call - HintAgent caches its meta lookup on them
        candidates = [
            CatalogEntry(f"{SPECIAL}/one.mp4", 30, "mix/special"),
            CatalogEntry(f"{GENERAL}/two.mp4", 30, "mix/general"),
        ]
        kept = HintAgent.filter_candidate_entries(when, candidates, meta_hints)
        return sorted(entry.tag for entry in kept)

    def test_no_meta_hints_keeps_everything(self):
        assert self._filter([], datetime(2026, 3, 1, 12)) == BOTH

    def test_untagged_content_is_never_restricted(self):
        # the hint covers mix/special, so mix/general is unaffected by it
        hints = [{"tags": [SPECIAL], "custom_holiday": "aug_day"}]
        assert self._filter(hints, datetime(2026, 1, 1, 12)) == GENERAL_ONLY

    def test_custom_holiday_fixed_date(self):
        hints = [{"tags": [SPECIAL], "custom_holiday": "aug_day"}]
        # Aug 29 2026 is a Saturday, and a fixed date is taken literally
        assert self._filter(hints, datetime(2026, 8, 29, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 8, 28, 12)) == GENERAL_ONLY
        assert self._filter(hints, datetime(2026, 8, 30, 12)) == GENERAL_ONLY

    def test_custom_holiday_ordinal_date(self):
        hints = [{"tags": [SPECIAL], "custom_holiday": "thanksgiving"}]
        # 4th thursday of november 2026 is the 26th
        assert self._filter(hints, datetime(2026, 11, 26, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 11, 25, 12)) == GENERAL_ONLY

    def test_week_number(self):
        hints = [{"tags": [SPECIAL], "week_number": 20}]
        # May 11 2026 is ISO week 20, May 18 is week 21
        assert self._filter(hints, datetime(2026, 5, 11, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 5, 18, 12)) == GENERAL_ONLY

    def test_week_number_accepts_every_value_form(self):
        for value in (20, "20", "week number 20"):
            hints = [{"tags": [SPECIAL], "week_number": value}]
            assert self._filter(hints, datetime(2026, 5, 11, 12)) == BOTH
            assert self._filter(hints, datetime(2026, 5, 18, 12)) == GENERAL_ONLY

    def test_month(self):
        hints = [{"tags": [SPECIAL], "month": "October"}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 11, 5, 12)) == GENERAL_ONLY

    def test_month_is_case_tolerant(self):
        # unlike a folder name, which has to be capitalized
        hints = [{"tags": [SPECIAL], "month": "october"}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH

    def test_quarter(self):
        hints = [{"tags": [SPECIAL], "quarter": "Q4"}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 5, 5, 12)) == GENERAL_ONLY

    def test_day_of_week(self):
        hints = [{"tags": [SPECIAL], "day_of_week": "friday"}]
        # March 6 2026 is a Friday
        assert self._filter(hints, datetime(2026, 3, 6, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 3, 7, 12)) == GENERAL_ONLY

    def test_day_of_week_is_case_tolerant(self):
        # constructed directly here rather than gated by test_pattern first
        hints = [{"tags": [SPECIAL], "day_of_week": "Friday"}]
        assert self._filter(hints, datetime(2026, 3, 6, 12)) == BOTH

    def test_day_of_week_rejects_a_name_that_is_not_a_day(self):
        hints = [{"tags": [SPECIAL], "day_of_week": "banana"}]
        with pytest.raises(ValueError, match="Day of week not valid"):
            self._filter(hints, datetime(2026, 3, 6, 12))

    def test_date_range(self):
        hints = [{"tags": [SPECIAL], "date_range": "December 1 - December 25"}]
        assert self._filter(hints, datetime(2025, 12, 10, 12)) == BOTH
        assert self._filter(hints, datetime(2025, 6, 10, 12)) == GENERAL_ONLY

    def test_day_part(self):
        hints = [{"tags": [SPECIAL], "day_part": "morning"}]
        assert self._filter(hints, datetime(2026, 3, 1, 7)) == BOTH
        assert self._filter(hints, datetime(2026, 3, 1, 20)) == GENERAL_ONLY

    def test_every_condition_in_an_entry_must_pass(self):
        hints = [{"tags": [SPECIAL], "week_number": 20, "day_part": "morning"}]
        assert self._filter(hints, datetime(2026, 5, 11, 7)) == BOTH
        # right week, wrong day part
        assert self._filter(hints, datetime(2026, 5, 11, 20)) == GENERAL_ONLY
        # right day part, wrong week
        assert self._filter(hints, datetime(2026, 5, 18, 7)) == GENERAL_ONLY

    def test_exclusive_takes_over_the_pool(self):
        hints = [{"tags": [SPECIAL], "custom_holiday": "aug_day", "exclusive": True}]
        assert self._filter(hints, datetime(2026, 8, 29, 12)) == SPECIAL_ONLY
        assert self._filter(hints, datetime(2026, 8, 28, 12)) == GENERAL_ONLY

    def test_unrecognized_key_is_not_a_condition(self):
        # captures current behavior - an unknown field is ignored rather than
        # rejected, so the tag ends up unrestricted
        hints = [{"tags": [SPECIAL], "not_a_hint": "whatever"}]
        assert self._filter(hints, datetime(2026, 3, 1, 12)) == BOTH
