import os
import sys
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add paths for module imports
cwd = os.getcwd()
parent = os.path.abspath(os.path.join(cwd, os.pardir))
sys.path.append(cwd)
sys.path.append(parent)

from fs42.station_manager import StationManager
from .api import routers

_shutdown_queue = None
player_command_queue = None

@asynccontextmanager
async def _lifespan(app):
    if _shutdown_queue is not None:
        async def shutdown_monitor():
            while True:
                await asyncio.sleep(1)
                try:
                    msg = _shutdown_queue.get_nowait()
                    if msg == "shutdown":
                        os._exit(0)
                except Exception:
                    pass
        asyncio.get_event_loop().create_task(shutdown_monitor())
    yield

# Create FastAPI app
fapi = FastAPI(title="FieldStation42 API", lifespan=_lifespan)

@fapi.get("/")
async def root():
    return FileResponse("fs42/fs42_server/static/index.html")

@fapi.get("/remote")
async def remote():
    return FileResponse("fs42/fs42_server/static/remote.html")

@fapi.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("fs42/fs42_server/static/favicon.ico")

# Include routers from the api package
for router in routers:
    fapi.include_router(router)


def run_with_shutdown_queue(shutdown_queue, command_queue):
    import logging

    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return ('/player/status' not in record.getMessage())

    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())

    global player_command_queue, _shutdown_queue
    player_command_queue = command_queue
    _shutdown_queue = shutdown_queue
    fapi.state.player_command_queue = command_queue

    fapi.mount("/static", StaticFiles(directory="fs42/fs42_server/static", html="true"), name="static")
    os.makedirs("runtime/guide_videos", exist_ok=True)
    fapi.mount("/guide_videos", StaticFiles(directory="runtime/guide_videos"), name="guide_videos")
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


def mount_fs42_api():
    import logging
    
    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return ('/player/status' not in record.getMessage())
    
    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())
    
    fapi.state.player_command_queue = None
    fapi.mount("/static", StaticFiles(directory="fs42/fs42_server/static", html="true"), name="static")
    os.makedirs("runtime/guide_videos", exist_ok=True)
    fapi.mount("/guide_videos", StaticFiles(directory="runtime/guide_videos"), name="guide_videos")
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


# Method 1: Basic uvicorn.run()
if __name__ == "__main__":
    mount_fs42_api()
