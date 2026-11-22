import logging
from unittest.mock import patch

import pytest

# station_manager has to be imported before station_io - see test_custom_holiday_names
from fs42.station_manager import StationManager
from fs42.station_io import StationIO

DOCS_EXAMPLE = {
    "server_port": 4242,
    "normalize_titles": True,
    "show_cable_box_time": True,
    "title_patterns": [
        {
            "pattern": "^\\[STUDIO\\][\\s._-]+(.+?)[\\s._-]+\\d{4}[\\s._-]+\\d+.*$",
            "group": 1,
            "description": "Studio releases with year and episode",
        },
    ],
    "day_parts": {
        "morning": {"start_hour": 6, "end_hour": 10},
        "daytime": {"start_hour": 10, "end_hour": 18},
        "prime": {"start_hour": 18, "end_hour": 23},
        "late": {"start_hour": 23, "end_hour": 2},
        "overnight": {"start_hour": 2, "end_hour": 6},
    },
    "schedule_agent": {"trigger_add_at": "day", "amount_to_add": "week"},
    "custom_holidays": {"thanksgiving": "4th thursday november", "christmas": "December 25"},
    "parental_controls_pin": "1234",
    "parental_controls_theme": "classic",
    "api_key": "correct-horse-battery-staple",
    "standby_image": "runtime/standby.png",
    "overlay_conf": {"overlay_effect": "drop_shadow", "overlay_text_color": [255, 255, 0, 255]},
}


def _load(config_data):
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    with patch.object(StationIO, "load_main_config", return_value=config_data):
        with patch("fs42.station_io.glob.glob", return_value=[]):
            return StationManager()


@pytest.mark.parametrize("conf", [{}, DOCS_EXAMPLE])
def test_valid_configs_pass(conf):
    assert StationIO().validate_main_config(conf) == (True, None)


@pytest.mark.parametrize("conf,expected", [
    ({"server_port": 0}, "server_port"),
    ({"server_port": "4242"}, "server_port"),
    ({"parental_controls_pin": "123"}, "parental_controls_pin: must be exactly four digits"),
    ({"parental_controls_theme": "neon"}, "parental_controls_theme"),
    ({"day_parts": {"prime": {"start_hour": 18, "end_hour": 24}}}, "day_parts.prime.end_hour"),
    ({"schedule_agent": {"trigger_add_at": "day"}}, "amount_to_add"),
    ({"title_patterns": [{"pattern": "(", "group": 1}]}, "title_patterns.0.pattern"),
    ({"custom_holidays": {"October": "August 1"}}, "MonthHint"),
    ({"custom_holidays": {"xmas": "Dec 25th"}}, "custom_holidays.xmas"),
    ({"api_key": "  "}, "api_key: can't be blank"),
    ({"recall_last_channel": "yes"}, "recall_last_channel"),
])
def test_invalid_configs_fail(conf, expected):
    ok, message = StationIO().validate_main_config(conf)
    assert not ok
    assert expected in message


def test_holiday_collides_with_a_day_part_from_the_new_config():
    conf = {"custom_holidays": {"insomnia": "August 1"},
            "day_parts": {"insomnia": {"start_hour": 1, "end_hour": 3}}}
    ok, message = StationIO().validate_main_config(conf)
    assert not ok and "DayPartHint" in message


def test_holiday_collides_with_a_built_in_day_part():
    ok, message = StationIO().validate_main_config({"custom_holidays": {"prime": "August 1"}})
    assert not ok and "DayPartHint" in message


def test_unknown_keys_pass_validation():
    assert StationIO().validate_main_config({"start_chanel": 3}) == (True, None)


def test_unknown_keys_get_suggestions():
    unknown = StationIO().unknown_main_config_keys({"start_chanel": 3, "zzz": 1, "show_cable_box_time": True})
    assert unknown == [
        {"key": "start_chanel", "suggestion": "start_channel"},
        {"key": "zzz", "suggestion": None},
    ]


def test_every_key_the_loader_reads_is_known():
    assert StationIO().unknown_main_config_keys(DOCS_EXAMPLE) == []


def test_loader_warns_about_unknown_keys(caplog):
    with caplog.at_level(logging.WARNING):
        _load({"start_chanel": 3})
    assert "unknown setting 'start_chanel' (did you mean 'start_channel'?)" in caplog.text


def test_standby_image_reaches_server_conf():
    manager = _load({"standby_image": "catalog/standby.png"})
    assert manager.server_conf["standby_image"] == "catalog/standby.png"
