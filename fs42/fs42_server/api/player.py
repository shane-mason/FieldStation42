from fastapi import APIRouter, Request
import json
from fs42.station_manager import StationManager

router = APIRouter(prefix="/player", tags=["player"])


@router.get("/status")
async def get_player_status():
    status_socket = StationManager().server_conf["status_socket"]
    if status_socket:
        try:
            with open(status_socket, "r") as f:
                status = f.read().strip()
            return {"status": status}
        except FileNotFoundError:
            return {"error": "Status socket file not found."}
    else:
        return {"error": "Status socket is not configured."}


@router.get("/channels/{channel}")
async def player_channel(channel: str):
    command = {"command": "direct", "channel": -1}
    if channel.isnumeric():
        command["channel"] = int(channel)
    elif channel == "up":
        command["command"] = "up"
    elif channel == "down":
        command["command"] = "down"
    else:
        return {"error": "Invalid channel command. Use a number, 'up', or 'down'."}

    cs = StationManager().server_conf["channel_socket"]
    with open(cs, "w") as f:
        f.write(json.dumps(command))
    return {"command": command}


@router.get("/commands/stop")
@router.post("/commands/stop")
async def player_stop(request: Request):
    command_queue = request.app.state.player_command_queue
    print("command q: ", command_queue)
    command_queue.put("exit")
    # Use command_queue here
    return {"status": "stopped"}
