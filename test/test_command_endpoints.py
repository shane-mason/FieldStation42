import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from fs42.fs42_server.api import player, ppv
from fs42.fs42_server.api.media import PROJECT_ROOT


def _request(queue, body=None):
    async def json():
        return body or {}
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(player_command_queue=queue)), json=json)


def _station_manager():
    manager = MagicMock()
    manager.return_value.station_by_channel.return_value = {"network_name": "PPV"}
    return manager


CALLS = {
    "guide": lambda req: player.show_guide(req),
    "stop": lambda req: player.player_stop(req),
    "ticker": lambda req: player.show_ticker(req),
    "break-in": lambda req: player.break_in(req),
    "web key": lambda req: player.send_web_key("NavRight", req),
    "ppv key": lambda req: ppv.send_key(70, "Enter", req),
    "ppv play_file": lambda req: ppv.play_file(70, ppv.PlayFileRequest(file_path=__file__), req),
}


@pytest.mark.parametrize("name", CALLS)
def test_disconnected_player_is_503(name):
    with patch("fs42.fs42_server.api.ppv.StationManager", _station_manager()):
        with pytest.raises(HTTPException) as err:
            asyncio.run(CALLS[name](_request(None)))
    assert err.value.status_code == 503


@pytest.mark.parametrize("key", sorted(player.WEB_KEYS))
def test_web_key_is_forwarded(key):
    queue = MagicMock()
    asyncio.run(player.send_web_key(key, _request(queue)))
    queue.put.assert_called_once_with({"command": "web_key", "key": key})


@pytest.mark.parametrize("key", ["ArrowLeft", "Escape", "a"])
def test_web_key_rejects_unknown_keys(key):
    queue = MagicMock()
    with pytest.raises(HTTPException) as err:
        asyncio.run(player.send_web_key(key, _request(queue)))
    assert err.value.status_code == 400
    queue.put.assert_not_called()


@pytest.mark.parametrize("name", [n for n in CALLS if n != "break-in"])
def test_connected_player_gets_the_command(name):
    queue = MagicMock()
    with patch("fs42.fs42_server.api.ppv.StationManager", _station_manager()):
        asyncio.run(CALLS[name](_request(queue, {"message": "hi"})))
    queue.put.assert_called_once()


def test_break_in_resolves_relative_path_from_project_root():
    queue = MagicMock()
    expected = os.path.join(PROJECT_ROOT, "docs", "static.mp4")
    asyncio.run(player.break_in(_request(queue, {"file_path": "docs/static.mp4"})))
    queue.put.assert_called_once_with({"command": "break_in", "file_path": expected})


def test_break_in_passes_absolute_path_through():
    queue = MagicMock()
    asyncio.run(player.break_in(_request(queue, {"file_path": __file__})))
    queue.put.assert_called_once_with({"command": "break_in", "file_path": __file__})


@pytest.mark.parametrize("body,status", [
    ({"file_path": "docs/no_such_video.mp4"}, 404),
    ({"file_path": "   "}, 400),
    ({}, 400),
])
def test_break_in_rejects_bad_paths(body, status):
    queue = MagicMock()
    with pytest.raises(HTTPException) as err:
        asyncio.run(player.break_in(_request(queue, body)))
    assert err.value.status_code == status
    queue.put.assert_not_called()
