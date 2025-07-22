import asyncio
import uvicorn
from fastapi import FastAPI
import os
import sys
from datetime import datetime
import json

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
cwd = os.getcwd()
parent = os.path.abspath(os.path.join(cwd, os.pardir))
sys.path.append(cwd)
sys.path.append(parent)

from fs42.station_manager import StationManager
from fs42.catalog_api import CatalogAPI
from fs42.liquid_api import LiquidAPI
from fs42.liquid_manager import LiquidManager

# Create your FastAPI app
fapi = FastAPI()


@fapi.get("/")
async def root():
    return FileResponse("fs42/fs42_server/static/index.html")


@fapi.get("/summary/")
async def get_summary():
    summaries = []
    for station in StationManager().stations:
        if station["_has_schedule"]:
            sched_summary = LiquidManager().get_summary_json(network_name=station["network_name"])
        else:
            sched_summary = {"network_name": station["network_name"], "start": 0, "end": 0}
        summary = {
            "network_name": station["network_name"],
            "channel_number": station["channel_number"],
            "catalog_summary": CatalogAPI.get_summary(station),
            "schedule_summary": sched_summary,
        }
        summaries.append(summary)
    return {"summary_data": summaries}


@fapi.get("/summary/stations")
async def get_stations():
    station_ids = [station["network_name"] for station in StationManager().stations]
    return {"network_names": station_ids}


@fapi.get("/summary/schedules")
async def get_schedule_summaries():
    summaries = LiquidManager().get_summary_json()
    return {"schedule_summaries": summaries}


@fapi.get("/summary/schedules/{network_name}")
async def get_schedule_summary(network_name: str):
    summary = LiquidManager().get_summary_json(network_name=network_name)
    return {"schedule_summary": summary}


@fapi.get("/summary/catalogs")
async def get_catalog_summary():
    summaries = []
    for station in StationManager().stations:
        catalog_entries = CatalogAPI.get_entries(station)
        summary = {"network_name": station["network_name"], "entry_count": len(catalog_entries)}
        summaries.append(summary)
    return {"catalog_summaries": summaries}


@fapi.get("/stations/{network_name}")
async def get_station_config(network_name: str):
    return {"network_name": network_name, "station_config": StationManager().station_by_name(network_name)}


@fapi.get("/catalogs/{network_name}")
async def get_catalog(network_name: str):
    conf = StationManager().station_by_name(network_name)
    catalog_entries = CatalogAPI.get_entries(conf)
    return {"network_name": network_name, "catalog_entries": catalog_entries}


@fapi.get("/catalogs/search/{network_name}")
async def search_catalog(network_name: str, query: str = None):
    conf = StationManager().station_by_name(network_name)
    if query:
        catalog_entries = CatalogAPI.search_entries(conf, query)
    else:
        catalog_entries = CatalogAPI.get_entries(conf)

    return {"network_name": network_name, "query": query, "catalog_entries": catalog_entries}


@fapi.get("/schedules/{network_name}")
async def get_schedule(network_name: str, start: str = None, end: str = None):
    conf = StationManager().station_by_name(network_name)
    sdt = None
    edt = None
    if start and end:
        try:
            sdt = datetime.fromisoformat(start)
            edt = datetime.fromisoformat(end)
        except ValueError:
            return {"error": "Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS) for start and end."}

    schedule_blocks = LiquidAPI.get_blocks(conf, sdt, edt)
    return {"network_name": network_name, "schedule_blocks": schedule_blocks}


@fapi.get("/player/status")
async def get_player_status():
    status_socket = StationManager().server_conf["status_socket"]
    if status_socket:
        try:
            with open(status_socket, 'r') as f:
                status = f.read().strip()
            return {"status": status}
        except FileNotFoundError:
            return {"error": "Status socket file not found."}
    else:   
        return {"error": "Status socket is not configured."}
    
@fapi.get("/player/channels/{channel}")
async def player_channel(channel: str):
    command =  {"command": "direct", "channel": -1}
    if channel.isnumeric():
        command["channel"] = int(channel)
    elif channel == "up":
        command["command"] = "up"
    elif channel == "down":
        command["command"] = "down"
    else:
        return {"error": "Invalid channel command. Use a number, 'up', or 'down'."}

    cs = StationManager().server_conf["channel_socket"]
    with open(cs, 'w') as f:
        f.write(json.dumps(command))
    return {"command": command} 


def run_with_shutdown_queue(shutdown_queue):
    """
    Run the FastAPI server and monitor the shutdown_queue for a shutdown message.
    """
    def start_shutdown_monitor():
        async def shutdown_monitor():
            while True:
                await asyncio.sleep(1)
                try:
                    msg = shutdown_queue.get_nowait()
                    if msg == "shutdown":
                        import os
                        os._exit(0)
                except Exception:
                    pass
        loop = asyncio.get_event_loop()
        loop.create_task(shutdown_monitor())

    fapi.mount("/static", StaticFiles(directory="fs42/fs42_server/static", html="true"), name="static")
    fapi.add_event_handler("startup", start_shutdown_monitor)
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])

def mount_fs42_api():
    fapi.mount("/static", StaticFiles(directory="fs42/fs42_server/static", html="true"), name="static")
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


# Method 1: Basic uvicorn.run()
if __name__ == "__main__":
    mount_fs42_api()