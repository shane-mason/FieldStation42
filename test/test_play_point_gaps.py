import datetime
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.liquid_manager import LiquidManager  # noqa: E402

START = datetime.datetime(2026, 10, 12, 20, 0)


def _manager(station_conf):
    block = SimpleNamespace(
        start_time=START,
        end_time=START + datetime.timedelta(minutes=30),
        title="Cartoons",
        plan=[SimpleNamespace(path="show.mp4", duration=1797)],
    )
    manager = LiquidManager.__new__(LiquidManager)
    manager.get_programming_block = lambda name, when: block
    stations = MagicMock()
    stations.return_value.station_by_name.return_value = station_conf
    return manager, stations


def _play_point(station_conf, when):
    manager, stations = _manager(station_conf)
    with patch("fs42.liquid_manager.StationManager", stations):
        return manager.get_play_point("Toons", when)


def test_inside_plan_returns_the_scheduled_entry():
    point = _play_point({"network_type": "standard"}, START + datetime.timedelta(seconds=100))
    assert point.index == 0 and point.offset == 100 and point.plan[0].path == "show.mp4"


def test_gap_after_plan_plays_brb_until_block_end():
    when = START + datetime.timedelta(seconds=1798)
    point = _play_point({"network_type": "standard", "be_right_back_media": "runtime/brb.png"}, when)
    assert [(e.path, e.duration) for e in point.plan] == [("runtime/brb.png", 2)]
    assert point.index == 0 and point.offset == 0 and point.block_title == "Cartoons"


def test_gap_without_brb_still_returns_nothing():
    assert _play_point({"network_type": "standard"}, START + datetime.timedelta(seconds=1798)) is None
