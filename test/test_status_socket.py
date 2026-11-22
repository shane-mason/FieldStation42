import json

import fs42.station_player as station_player


class _FakeStationManager:
    def __init__(self, path):
        self.server_conf = {"status_socket": str(path)}


def _write_status(tmp_path, monkeypatch, **kwargs):
    socket = tmp_path / "play_status.socket"
    monkeypatch.setattr(station_player, "StationManager", lambda: _FakeStationManager(socket))
    station_player.update_status_socket("playing", "WFS", 3, **kwargs)
    return json.loads(socket.read_text())


def test_metadata_is_merged(tmp_path, monkeypatch):
    status = _write_status(tmp_path, monkeypatch, metadata={"show_title": "Lost", "season": 4})
    assert status["show_title"] == "Lost"
    assert status["season"] == 4


def test_metadata_never_overrides_player_fields(tmp_path, monkeypatch):
    status = _write_status(
        tmp_path, monkeypatch,
        title="Block Title", duration="10:00", content_type="feature",
        metadata={"title": "NFO Title", "duration": 1, "content_type": "music", "network_name": "X"},
    )
    assert status["title"] == "Block Title"
    assert status["duration"] == "10:00"
    assert status["content_type"] == "feature"
    assert status["network_name"] == "WFS"


def test_content_rating_is_normalized(tmp_path, monkeypatch):
    status = _write_status(tmp_path, monkeypatch, metadata={"content_rating": "Rated PG-13"})
    assert status["content_rating"] == "PG-13"


def test_no_metadata_has_no_rating(tmp_path, monkeypatch):
    status = _write_status(tmp_path, monkeypatch)
    assert "content_rating" not in status
