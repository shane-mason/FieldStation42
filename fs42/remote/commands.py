import json
import os
import time
import traceback

SOCKET_PATH = "runtime/channel.socket"
STATUS_SOCKET_PATH = "runtime/play_status.socket"  # Update with real path

def read_status():
    try:
        with open(STATUS_SOCKET_PATH, "r") as fifo:
            line = fifo.readline()
            status = json.loads(line)
            return {
                "channel": status.get("channel_number", -1),
                "name": status.get("network_name", ""),
                "title": status.get("title", ""),
            }
    except Exception:
        traceback.print_exc()
        return {"channel": -1, "name": ""}

def write_command(message: dict):
    """Takes a dictionary command"""
    message = json.dumps(message) + "\n"
    print("Writing to FIFO:", message)

    if not os.path.exists(SOCKET_PATH):
        raise Exception(f"FIFO not found: {SOCKET_PATH}")
    with open(SOCKET_PATH, "w") as fifo:
        fifo.write(message)
        fifo.flush()

    # Give the player a moment to update status
    time.sleep(.25)

    status = read_status()
    return status