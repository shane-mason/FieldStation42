import os
import sys
import asyncio
import uvicorn
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

# Create FastAPI app
fapi = FastAPI(title="FieldStation42 API")
player_command_queue = None

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

    global player_command_queue
    player_command_queue = command_queue
    fapi.state.player_command_queue = command_queue

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
    import logging
    
    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return ('/player/status' not in record.getMessage())
    
    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())
    
    fapi.state.player_command_queue = None
    fapi.mount("/static", StaticFiles(directory="fs42/fs42_server/static", html="true"), name="static")
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


# Method 1: Basic uvicorn.run()
if __name__ == "__main__":
    mount_fs42_api()
