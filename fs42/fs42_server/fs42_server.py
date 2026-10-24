import os
import sys
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

# Add paths for module imports
cwd = os.getcwd()
parent = os.path.abspath(os.path.join(cwd, os.pardir))
sys.path.append(cwd)
sys.path.append(parent)

from fs42.station_manager import StationManager, StationConfigError
from .api import routers
from . import auth

_shutdown_queue = None
player_command_queue = None

# browsers must check for updated files on every load, or they keep running old UI code after an update
REVALIDATE = {"Cache-Control": "no-cache"}


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers.update(REVALIDATE)
        return response

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
fapi.middleware("http")(auth.auth_middleware)


@fapi.exception_handler(StationConfigError)
async def _station_config_error_handler(request: Request, exc: StationConfigError):
    # Configuration problems are the operator's to fix, not a server fault -
    # report them instead of letting them take the request (or the process) down
    logging.getLogger("FS42SERVER").error(f"Station configuration error: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})

@fapi.get("/")
async def root():
    return FileResponse("fs42/fs42_server/static/index.html", headers=REVALIDATE)

@fapi.get("/remote")
async def remote():
    return FileResponse("fs42/fs42_server/static/remote.html", headers=REVALIDATE)

@fapi.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("fs42/fs42_server/static/favicon.ico")

@fapi.get("/login", include_in_schema=False)
async def login_page(request: Request, next: str = "/", api_key: str = None):
    key = StationManager().api_key()
    if key is None:
        return RedirectResponse(auth.safe_next(next), status_code=302)
    if api_key is not None:
        if auth.login_blocked(request):
            return JSONResponse(status_code=429, content={"detail": "too many failed attempts - try again later"})
        if auth.key_matches(api_key, key):
            auth.clear_login_failures(request)
            response = RedirectResponse(auth.safe_next(next), status_code=302)
            auth.set_session_cookie(response, key)
            return response
        auth.record_login_failure(request)
    return FileResponse("fs42/fs42_server/static/login.html", headers=REVALIDATE)

@fapi.post("/login", include_in_schema=False)
async def login(request: Request):
    key = StationManager().api_key()
    if key is None:
        return {"status": "ok"}
    if auth.login_blocked(request):
        return JSONResponse(status_code=429, content={"detail": "too many failed attempts - try again later"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    candidate = body.get("api_key") if isinstance(body, dict) else None
    if not isinstance(candidate, str) or not auth.key_matches(candidate, key):
        auth.record_login_failure(request)
        return JSONResponse(status_code=401, content={"detail": "invalid api key"})
    auth.clear_login_failures(request)
    response = JSONResponse(content={"status": "ok"})
    auth.set_session_cookie(response, key)
    return response

@fapi.post("/logout", include_in_schema=False)
async def logout():
    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response

# Include routers from the api package
for router in routers:
    fapi.include_router(router)


def _mount_static():

    follow_symlink = StationManager().server_conf.get("follow_static_symlinks", False)
    if follow_symlink:
        logging.getLogger("FS42SERVER").warning(
            "follow_static_symlinks is on - symlinks in fs42/fs42_server/static and "
            "runtime/guide_videos will be served even if they point outside of those directories."
        )

    fapi.mount(
        "/static",
        RevalidatingStaticFiles(directory="fs42/fs42_server/static", html="true", follow_symlink=follow_symlink),
        name="static",
    )
    os.makedirs("runtime/guide_videos", exist_ok=True)
    fapi.mount(
        "/guide_videos",
        StaticFiles(directory="runtime/guide_videos", follow_symlink=follow_symlink),
        name="guide_videos",
    )


class PlayerStatusFilter(logging.Filter):
    def filter(self, record):
        return ('/player/status' not in record.getMessage())


def _serve():
    access_log = logging.getLogger("uvicorn.access")
    access_log.addFilter(PlayerStatusFilter())
    access_log.addFilter(auth.ApiKeyLogFilter())

    _mount_static()
    auth.log_security_status()
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


def run_with_shutdown_queue(shutdown_queue, command_queue):
    global player_command_queue, _shutdown_queue
    player_command_queue = command_queue
    _shutdown_queue = shutdown_queue
    fapi.state.player_command_queue = command_queue
    _serve()


def mount_fs42_api():
    fapi.state.player_command_queue = None
    _serve()


# Method 1: Basic uvicorn.run()
if __name__ == "__main__":
    mount_fs42_api()
