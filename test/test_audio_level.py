import pytest
from unittest.mock import MagicMock

from fs42.audio_level import loudnorm_af


class TestLoudnormAf:
    def test_true_uses_defaults(self):
        assert loudnorm_af(True) == "@fs42level:lavfi=[loudnorm=I=-18:LRA=7:TP=-1.5,aresample=48000]"

    def test_overrides_merge_with_defaults(self):
        af = loudnorm_af({"i": -16, "tp": -2})
        assert "I=-16:LRA=7:TP=-2," in af

    @pytest.mark.parametrize("setting", [None, False, "yes", 1, [], {"i": "loud"}, {"i": True}])
    def test_off_or_invalid(self, setting):
        assert loudnorm_af(setting) is None

    @pytest.mark.parametrize("setting", [{"i": 0}, {"i": -100}, {"lra": 0}, {"lra": 99}, {"tp": 3}])
    def test_out_of_range_is_rejected(self, setting):
        assert loudnorm_af(setting) is None


tk = pytest.importorskip("tkinter")  # station_player imports the Tk guide

from fs42.station_player import StationPlayer  # noqa: E402


def _player(config):
    player = StationPlayer.__new__(StationPlayer)
    player._l = MagicMock()
    player.mpv = MagicMock()
    player.station_config = config
    return player


class TestSetStreamLeveling:
    def test_adds_filter_when_enabled(self):
        player = _player({"stream_loudnorm": True})
        player._set_stream_leveling(True)
        player.mpv.command.assert_any_call("af", "remove", "@fs42level")
        assert player.mpv.command.call_args[0][:2] == ("af", "add")

    def test_off_by_default(self):
        player = _player({})
        player._set_stream_leveling(True)
        assert all(c[0][1] != "add" for c in player.mpv.command.call_args_list)

    def test_not_added_for_local_files(self):
        player = _player({"stream_loudnorm": True})
        player._set_stream_leveling(False)
        assert all(c[0][1] != "add" for c in player.mpv.command.call_args_list)

    def test_remove_failure_is_ignored(self):
        player = _player({"stream_loudnorm": True})
        player.mpv.command.side_effect = [Exception("no such filter"), None]
        player._set_stream_leveling(True)
        assert player.mpv.command.call_count == 2

    def test_invalid_setting_warns_and_skips(self):
        player = _player({"stream_loudnorm": {"i": 5}})
        player._set_stream_leveling(True)
        player._l.warning.assert_called_once()
        assert all(c[0][1] != "add" for c in player.mpv.command.call_args_list)
