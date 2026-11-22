import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fs42.catalog import ShowCatalog
from fs42.catalog_entry import CatalogEntry, MatchingContentNotFound, NoFillerContentFound
from fs42.liquid_blocks import LiquidBlock
from fs42.liquid_schedule import LiquidSchedule
from fs42.timings import DAYS


def test_probability_is_resolved_per_bump():
    catalog = ShowCatalog({"network_name": "test", "bump_dir": "default"}, load=False)
    catalog.clip_index = {
        tag: [CatalogEntry(f"{tag}/bump.mp4", 10, tag)]
        for tag in ("default", "special")
    }
    spec = {"tags": "special", "chance": 0.75}
    with patch("fs42.catalog.random.random", side_effect=[0.74, 0.75, 0.9]) as draw:
        paths = [catalog.find_bump(20, datetime.datetime(2026, 1, 1), bump_tag=spec).path for _ in range(3)]
        assert paths == ["special/bump.mp4", "default/bump.mp4", "default/bump.mp4"]
        assert draw.call_count == 3
    assert spec == {"tags": "special", "chance": 0.75}
    with patch("fs42.catalog.random.random") as draw:
        for spec, expected in [("special", "special"), (None, "default"), ({"tags": "special", "chance": 0}, "default"),
                               ({"tags": "special", "chance": 1}, "special"), ({"tags": "special"}, "special")]:
            assert catalog.find_bump(20, datetime.datetime(2026, 1, 1), bump_tag=spec).tag == expected
        draw.assert_not_called()


@pytest.mark.parametrize("spec", [
    ["special", 0.75], {}, {"chance": 0.5}, {"tags": 42}, {"tags": None},
    {"tags": "special", "chance": 0.5, "extra": 1}, {"tags": "special", "probability": 0.5},
    {"tags": "special", "chance": "0.5"}, {"tags": "special", "chance": None},
    {"tags": "special", "chance": True}, {"tags": "special", "chance": -0.1},
    {"tags": "special", "chance": 1.1}, {"tags": "special", "chance": float("nan")},
    {"tags": "special", "chance": float("inf")}, {"tags": "special", "chance": -float("inf")},
])
def test_invalid_specs_fail_in_harvesting_and_selection(spec):
    catalog = ShowCatalog({"network_name": "test", "bump_dir": "default"}, load=False)
    with pytest.raises(ValueError, match="Invalid bump specification"):
        catalog._harvest_slot({"bump_dir": spec}, {}, {}, {}, {}, {})
    with pytest.raises(ValueError, match="Invalid bump specification"):
        catalog.find_bump(20, datetime.datetime(2026, 1, 1), bump_tag=spec)


def test_build_harvests_directory_strings_without_sampling():
    config = {day: {} for day in DAYS}
    config.update(network_name="test", content_dir="/media", bump_dir="default", clip_shows={})
    config["monday"] = {"20": {"bump_dir": {"tags": "special", "chance": 0}}}
    config["tag_overrides"] = {"show": {"bump_dir": {"tags": "special", "chance": 0.75}}}
    config["date_overrides"] = {"2026-01-01": {"20": {"bump_dir": {"tags": "date"}}}}
    config["week_overrides"] = {"1": {"monday": {"20": {"bump_dir": {"tags": "default", "chance": 0.5}}}}}
    catalog = ShowCatalog(config, load=False)
    with patch.object(catalog, "_scan_directory", return_value=0) as scan, \
            patch("fs42.catalog.CatalogAPI.set_entries"), \
            patch("fs42.catalog.os.path.isdir", return_value=False), \
            patch("fs42.catalog.random.random") as draw:
        catalog._build_standard()
    assert [call.args[0] for call in scan.call_args_list] == ["default", "special", "date"]
    draw.assert_not_called()


@pytest.mark.parametrize("tag,path", [
    ("sitcoms", "/media/sitcoms/show/episode.mp4"),
    ("sitcoms/show", "/media/elsewhere/episode.mp4"),
])
def test_scheduler_block_and_reel_preserve_per_bump_choice(tag, path):
    config = {
        "network_name": "test", "content_dir": "/media", "bump_dir": "default",
        "commercial_dir": "commercials", "commercial_free": False,
        "break_strategy": "standard", "schedule_increment": 30,
        "tag_overrides": {"sitcoms/show": {
            "bump_dir": {"tags": "special", "chance": 0.75}, "commercial_dir": "special-commercials",
            "start_bump": "opening.mp4", "end_bump": "closing.mp4",
        }},
    }
    catalog = ShowCatalog(config, load=False)
    catalog.clip_index = {
        key: [CatalogEntry(f"{key}/bump.mp4", 10, key)]
        for key in ("special-prebump", "default-postbump", "special-commercials")
    }
    catalog.clip_index["start_bumps"] = [CatalogEntry("opening.mp4", 5, "start_bumps")]
    catalog.clip_index["end_bumps"] = [CatalogEntry("closing.mp4", 5, "end_bumps")]
    schedule = LiquidSchedule.__new__(LiquidSchedule)
    schedule.conf = config
    schedule.catalog = catalog
    info, strategy, _ = schedule._break_info({"bump_dir": "slot"}, tag, path)
    assert json.loads(json.dumps(info)) == info
    now = datetime.datetime(2026, 1, 1)
    block = LiquidBlock(CatalogEntry(path, 60, tag), now, now + datetime.timedelta(seconds=90),
                        break_strategy=strategy, break_info=info)
    assert block.start_bump["path"] == "opening.mp4"
    assert block.end_bump["path"] == "closing.mp4"
    with patch("fs42.catalog.random.random", side_effect=[0.1, 0.9]):
        reel = catalog.make_reel_block(now, target_duration=30, bump_dir=block.bump_override,
                                       commercial_dir=block.commercial_override)
    assert reel.start_bump.path == "special-prebump/bump.mp4"
    assert reel.end_bump.path == "default-postbump/bump.mp4"
    assert reel.comms[0].tag == "special-commercials"
    assert info["bump_dir"] == {"tags": "special", "chance": 0.75}


def test_commercial_free_fill_samples_each_bump():
    catalog = ShowCatalog({
        "network_name": "test", "bump_dir": "default", "commercial_free": True,
        "break_duration": 20, "break_strategy": "end",
    }, load=False)
    catalog.clip_index = {
        tag: [CatalogEntry(f"{tag}/bump.mp4", 10, tag)] for tag in ("special", "default")
    }
    with patch("fs42.catalog.SlotReader.get_break_info", return_value={"break_strategy": "end"}), \
            patch("fs42.catalog.random.random", side_effect=[0.1, 0.9]):
        blocks = catalog.make_reel_fill(datetime.datetime(2026, 1, 1), 20,
                                        use_bumpers=False, bump_dir={"tags": "special", "chance": 0.75})
    assert [clip.tag for block in blocks for clip in block.comms] == ["special", "default"]
    # A full reel does not fit, so the remaining gap uses individual bump selections.
    with patch("fs42.catalog.SlotReader.get_break_info", return_value={"break_strategy": "standard"}), \
            patch("fs42.catalog.random.random", side_effect=[0.1, 0.9, 0.9, 0.1]):
        blocks = catalog.make_reel_fill(datetime.datetime(2026, 1, 1), 15,
                                        use_bumpers=False, bump_dir={"tags": "special", "chance": 0.75})
    assert [clip.tag for block in blocks for clip in block.comms] == ["default"]


def test_chosen_pool_keeps_filtering_lookahead_and_missing_content_errors():
    catalog = ShowCatalog({"network_name": "test", "bump_dir": "default"}, load=False)
    catalog.clip_index = {
        "default": [CatalogEntry("default.mp4", 5, "default")],
        "special": [CatalogEntry("too-long.mp4", 20, "special"),
                    CatalogEntry("wrong-hint.mp4", 5, "special", hints=["blocked"])],
        "next/--show": [CatalogEntry("next.mp4", 5, "next/--show")],
    }
    now = datetime.datetime(2026, 1, 1)
    with patch("fs42.catalog.MediaProcessor._test_candidate_hints", side_effect=lambda hints, when: not hints):
        with pytest.raises(MatchingContentNotFound, match="tag=special"):
            catalog.find_bump(20, now, bump_tag={"tags": "special", "chance": 1})
        assert catalog.find_bump(20, now, bump_tag={"tags": "special", "chance": 1}, lookahead=["current", "show"]).path == "next.mp4"
        catalog.clip_index["special"] = []
        with pytest.raises(MatchingContentNotFound, match="tag=special"):
            catalog.find_bump(20, now, bump_tag={"tags": "special", "chance": 1})
        with pytest.raises(NoFillerContentFound, match="tag=missing"):
            catalog.find_bump(20, now, bump_tag={"tags": "missing"})


def test_station_schema_declares_object_form_for_slot_bump_dir():
    schema = json.loads((Path(__file__).parents[1] / "fs42/station_config_schema.json").read_text())
    station = schema["properties"]["station_conf"]["properties"]
    slot_ref = {"$ref": "#/$defs/timeSlotConfig"}
    # Every slot-level location routes through timeSlotConfig.
    assert station["tag_overrides"]["additionalProperties"] == slot_ref
    assert station["slot_overrides"]["additionalProperties"] == slot_ref
    assert schema["$defs"]["daySchedule"]["oneOf"][1]["additionalProperties"] == slot_ref
    assert station["date_overrides"]["additionalProperties"]["oneOf"][1]["additionalProperties"] == slot_ref
    assert station["bump_dir"]["type"] == "string"

    branches = schema["$defs"]["timeSlotConfig"]["properties"]["bump_dir"]["oneOf"]
    assert branches[0] == {"type": "string"}
    assert branches[1] == {
        "type": "object",
        "properties": {
            "tags": {"type": "string"},
            "chance": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["tags"],
        "additionalProperties": False,
    }
    assert len(branches) == 2
