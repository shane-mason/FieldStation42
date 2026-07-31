import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from fs42.hometv import (
    ChannelNotFound,
    ProgramNotFound,
    UnsafeMediaPath,
    WatchError,
)

router = APIRouter(prefix="/api/watch", tags=["watch"])


class SessionRequest(BaseModel):
    channel: str
    profile: str = "auto"


def _manager(request: Request):
    manager = getattr(request.app.state, "hls_sessions", None)
    if manager is None:
        raise HTTPException(503, "Streaming service is not initialized")
    return manager


def _watch_error(exc: Exception):
    if isinstance(exc, ChannelNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (ProgramNotFound, UnsafeMediaPath)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.get("/channels")
async def channels(request: Request):
    return {"channels": _manager(request).resolver.channels()}


@router.get("/channels/{channel}/now")
async def now(channel: str, request: Request):
    try:
        resolver = _manager(request).resolver
        timestamp = __import__("datetime").datetime.now()
        return resolver.now(channel, timestamp).public_dict(timestamp)
    except WatchError as exc:
        raise _watch_error(exc)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionRequest, request: Request):
    try:
        session, airing = _manager(request).create(body.channel, body.profile)
        return {
            "session_id": session.session_id,
            "playlist_url": f"/api/watch/sessions/{session.session_id}/master.m3u8",
            "now": airing.public_dict(__import__("datetime").datetime.now()),
        }
    except (WatchError, ValueError) as exc:
        raise _watch_error(exc)
    except FileNotFoundError:
        raise HTTPException(503, "FFmpeg is not installed or not executable")


@router.get("/sessions/{session_id}/master.m3u8")
async def playlist(session_id: str, request: Request):
    return await _serve_asset(session_id, "master.m3u8", request)


@router.get("/sessions/{session_id}/{asset}")
async def segment(session_id: str, asset: str, request: Request):
    return await _serve_asset(session_id, asset, request)


async def _serve_asset(session_id: str, asset: str, request: Request):
    manager = _manager(request)
    try:
        path = manager.asset(session_id, asset)
    except KeyError:
        raise HTTPException(404, "Stream session not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # FFmpeg startup is asynchronous. Briefly wait for the first playlist.
    if asset == "master.m3u8":
        for _ in range(40):
            if path.is_file():
                break
            session = manager.get(session_id)
            if session.process.poll() is not None:
                raise HTTPException(502, "FFmpeg exited before creating a playlist")
            await asyncio.sleep(0.1)
    if not path.is_file():
        raise HTTPException(404, "HLS asset is not ready")
    media_type = (
        "application/vnd.apple.mpegurl"
        if path.suffix == ".m3u8"
        else "video/mp2t"
    )
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/sessions/{session_id}/heartbeat", status_code=204)
async def heartbeat(session_id: str, request: Request):
    try:
        _manager(request).get(session_id)
    except KeyError:
        raise HTTPException(404, "Stream session not found")
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    if not _manager(request).delete(session_id):
        raise HTTPException(404, "Stream session not found")
    return Response(status_code=204)
