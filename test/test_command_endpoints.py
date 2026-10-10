import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from fs42.fs42_server.api import player, ppv


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
    "ppv key": lambda req: ppv.send_key(70, "Enter", req),
    "ppv play_file": lambda req: ppv.play_file(70, ppv.PlayFileRequest(file_path=__file__), req),
}


@pytest.mark.parametrize("name", CALLS)
def test_disconnected_player_is_503(name):
    with patch("fs42.fs42_server.api.ppv.StationManager", _station_manager()):
        with pytest.raises(HTTPException) as err:
            asyncio.run(CALLS[name](_request(None)))
    assert err.value.status_code == 503


@pytest.mark.parametrize("name", CALLS)
def test_connected_player_gets_the_command(name):
    queue = MagicMock()
    with patch("fs42.fs42_server.api.ppv.StationManager", _station_manager()):
        asyncio.run(CALLS[name](_request(queue, {"message": "hi"})))
    queue.put.assert_called_once()
