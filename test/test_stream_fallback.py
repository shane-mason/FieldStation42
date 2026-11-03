"""A stub whose URL will not load must not hang the player or stall the remote."""
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("tkinter")  # station_player imports the Tk guide

from fs42.station_player import PlayerOutcome, PlayerState, StationPlayer  # noqa: E402


def _player(input_responses):
    player = StationPlayer.__new__(StationPlayer)
    player._l = MagicMock()
    player._pending_response = None
    player._active_afx = None
    player.skip_reception_check = False
    player.scrambler = None
    player.station_config = {"network_name": "test", "channel_number": 3}
    player.mpv = MagicMock()
    player.mpv.time_pos = None  # never starts playing
    responses = iter(input_responses)
    player.input_check_fn = lambda: next(responses, None)
    player._apply_vfx = MagicMock()
    return player


def _stub(tmp_path):
    p = tmp_path / "ep.strm"
    p.write_text("https://example.invalid/ep.mp4\n#duration=60\n", encoding="utf-8")
    return str(p)


@patch("fs42.station_player.update_status_socket", MagicMock())
@patch("fs42.station_player.StationManager")
def test_channel_change_interrupts_a_stub_that_is_still_loading(manager, tmp_path):
    manager.return_value.server_conf = {"video_seek_timeout": 5}
    change = PlayerOutcome(PlayerState.CHANNEL_CHANGE)
    player = _player([None, change])
    player.handle_runtime_command_outcome = lambda r: False
    player.is_non_interrupting = lambda r: False

    assert player.play_file(_stub(tmp_path), file_duration=60, offset_seconds=0) is False
    assert player._pending_response is change


@patch("fs42.station_player.update_status_socket", MagicMock())
@patch("fs42.station_player.StationManager")
def test_stub_that_never_loads_times_out(manager, tmp_path):
    manager.return_value.server_conf = {"video_seek_timeout": 0.2}
    player = _player([])
    assert player.play_file(_stub(tmp_path), file_duration=60, offset_seconds=0) is False
    assert player._pending_response is None
