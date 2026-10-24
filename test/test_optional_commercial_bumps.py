import datetime
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fs42.catalog import ShowCatalog
from fs42.catalog_entry import MatchingContentNotFound, NoFillerContentFound
from fs42.liquid_blocks import LiquidBlock

MONDAY_8PM = datetime.datetime(2026, 10, 12, 20, 0)


def _catalog():
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = {
        "network_name": "T",
        "break_strategy": "standard",
        "break_duration": 120,
        "commercial_free": False,
        "commercial_dir": "commercials",
    }
    catalog.clip_index = {
        "bump": [SimpleNamespace(path="bump.mp4", duration=5, hints=[], tag="bump", count=0)],
        "bump-prebump": [],
        "bump-postbump": [],
    }
    catalog._l = logging.getLogger("test")
    catalog.min_gap = 3

    def find_commercial(seconds, when, commercial_dir=None):
        if seconds < 30:
            raise MatchingContentNotFound("nothing fits")
        return SimpleNamespace(path="ad.mp4", duration=30, content_type="commercial", media_type="video")

    catalog.find_commercial = find_commercial
    return catalog


def test_commercial_reel_omits_bumps_without_a_bump_directory():
    block = _catalog().make_reel_block(MONDAY_8PM, target_duration=120)

    assert block.start_bump is None
    assert block.end_bump is None
    assert [entry.path for entry in block.comms] == ["ad.mp4"] * 4


def test_missed_slot_bump_override_without_station_default_omits_bumps():
    with patch("fs42.catalog.random.random", return_value=0.99):
        block = _catalog().make_reel_block(
            MONDAY_8PM,
            target_duration=120,
            bump_dir={"tags": "special", "chance": 0.5},
        )

    assert block.start_bump is None
    assert block.end_bump is None
    assert [entry.path for entry in block.comms] == ["ad.mp4"] * 4


def test_selected_slot_bump_directory_is_used_without_station_default():
    catalog = _catalog()
    catalog.clip_index["special"] = [
        SimpleNamespace(path="special.mp4", duration=5, hints=[], tag="special", count=0)
    ]

    block = catalog.make_reel_block(MONDAY_8PM, target_duration=120, bump_dir="special")

    assert block.start_bump.path == "special.mp4"
    assert block.end_bump.path == "special.mp4"


def test_commercial_free_reel_still_requires_bump_media():
    catalog = _catalog()
    catalog.config["commercial_free"] = True

    with pytest.raises(NoFillerContentFound, match="no bump directory is configured"):
        catalog.make_reel_block(MONDAY_8PM, target_duration=120)


def test_explicit_start_and_end_bumps_remain_without_a_bump_directory():
    content = SimpleNamespace(
        path="show.mp4", realpath="show.mp4", duration=60, title="Show",
        content_type="feature", media_type="video",
    )
    start_bump = {"path": "start.mp4", "duration": 5}
    end_bump = {"path": "end.mp4", "duration": 5}
    block = LiquidBlock(
        content,
        MONDAY_8PM,
        MONDAY_8PM + datetime.timedelta(seconds=120),
        break_info={
            "start_bump": start_bump,
            "end_bump": end_bump,
            "bump_dir": None,
            "commercial_dir": "commercials",
        },
    )

    with patch("fs42.liquid_blocks.FluidBuilder") as fluid_builder:
        fluid_builder.return_value.get_chapters.return_value = []
        fluid_builder.return_value.get_breaks.return_value = []
        block.make_plan(_catalog())

    assert block.plan[0].path == "start.mp4"
    assert block.plan[-1].path == "end.mp4"
