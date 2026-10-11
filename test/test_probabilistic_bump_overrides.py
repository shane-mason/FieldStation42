import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft7Validator

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
    spec = ["special", 0.75]
    with patch("fs42.catalog.random.random", side_effect=[0.74, 0.75, 0.9]) as draw:
        paths = [catalog.find_bump(20, datetime.datetime(2026, 1, 1), bump_tag=spec).path for _ in range(3)]
        assert paths == ["special/bump.mp4", "default/bump.mp4", "default/bump.mp4"]
        assert draw.call_count == 3
    assert spec == ["special", 0.75]
    with patch("fs42.catalog.random.random") as draw:
        for spec, expected in [("special", "special"), (None, "default"), (["special", 0], "default"), (["special", 1], "special")]:
            assert catalog.find_bump(20, datetime.datetime(2026, 1, 1), bump_tag=spec).tag == expected
        draw.assert_not_called()


@pytest.mark.parametrize("spec", [
    [], ["special"], ["special", 0.5, 1], [42, 0.5],
    ["special", "0.5"], ["special", None], ["special", True],
    ["special", -0.1], ["special", 1.1],
    ["special", float("nan")], ["special", float("inf")], ["special", -float("inf")],
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
    config["monday"] = {"20": {"bump_dir": ["special", 0]}}
    config["tag_overrides"] = {"show": {"bump_dir": ["special", 0.75]}}
    config["date_overrides"] = {"2026-01-01": {"20": {"bump_dir": ["date", 1]}}}
    config["week_overrides"] = {"1": {"monday": {"20": {"bump_dir": ["default", 0.5]}}}}
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
            "bump_dir": ["special", 0.75], "commercial_dir": "special-commercials",
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
    assert info["bump_dir"] == ["special", 0.75]


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
                                        use_bumpers=False, bump_dir=["special", 0.75])
    assert [clip.tag for block in blocks for clip in block.comms] == ["special", "default"]
    # A full reel does not fit, so the remaining gap uses individual bump selections.
    with patch("fs42.catalog.SlotReader.get_break_info", return_value={"break_strategy": "standard"}), \
            patch("fs42.catalog.random.random", side_effect=[0.1, 0.9, 0.9, 0.1]):
        blocks = catalog.make_reel_fill(datetime.datetime(2026, 1, 1), 15,
                                        use_bumpers=False, bump_dir=["special", 0.75])
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
            catalog.find_bump(20, now, bump_tag=["special", 1])
        assert catalog.find_bump(20, now, bump_tag=["special", 1], lookahead=["current", "show"]).path == "next.mp4"
        catalog.clip_index["special"] = []
        with pytest.raises(MatchingContentNotFound, match="tag=special"):
            catalog.find_bump(20, now, bump_tag=["special", 1])
        with pytest.raises(NoFillerContentFound, match="tag=missing"):
            catalog.find_bump(20, now, bump_tag=["missing", 1])


def test_station_schema_accepts_only_supported_override_forms():
    schema = json.loads((Path(__file__).parents[1] / "fs42/station_config_schema.json").read_text())
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    valid_specs = ["special", ["special", 0], ["special", 0.75], ["special", 1]]
    invalid_specs = [[], ["special"], ["special", 0.5, 1], [42, 0.5],
                     ["special", "0.5"], ["special", None], ["special", True],
                     ["special", -0.1], ["special", 1.1]]
    for valid, specs in [(True, valid_specs), (False, invalid_specs)]:
        for spec in specs:
            slot = {"tags": "show", "bump_dir": spec}
            for overrides in [
                {"tag_overrides": {"show": slot}},
                {"slot_overrides": {"evening": slot}},
                {"monday": {"20": slot}},
                {"date_overrides": {"January 1": {"20": slot}}},
                {"week_overrides": {"January 1 - January 7": {"monday": {"20": slot}}}},
            ]:
                station = {"network_name": "test", "channel_number": 1,
                           "bump_dir": "default", **overrides}
                assert validator.is_valid({"station_conf": station}) == valid
    assert not validator.is_valid({"station_conf": {
        "network_name": "test", "channel_number": 1, "bump_dir": ["special", 0.75],
    }})
