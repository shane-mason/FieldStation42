import os
import mimetypes
import logging
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/media", tags=["media"])
logger = logging.getLogger("media_api")

AUDIO_EXTENSIONS = {'.mp3', '.ogg', '.wav', '.flac', '.aac', '.m4a', '.opus'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'}

# project root: fs42/fs42_server/api/media.py -> up three levels
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

GUIDE_VIDEOS_DIR = os.path.join(PROJECT_ROOT, 'runtime', 'guide_videos')


def safe_resolve(relative_path):
    clean = relative_path.lstrip('/').lstrip('\\')
    resolved = os.path.realpath(os.path.join(PROJECT_ROOT, clean))
    if not resolved.startswith(PROJECT_ROOT):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid path")
    return resolved


@router.get("/list")
async def list_media(path: str, type: str = "audio"):
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"path not found: {path}")
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path is not a directory")

    if type == "video":
        allowed = VIDEO_EXTENSIONS
    elif type == "any":
        allowed = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
    else:
        allowed = AUDIO_EXTENSIONS

    try:
        files = sorted(
            f for f in os.listdir(resolved)
            if os.path.isfile(os.path.join(resolved, f))
            and os.path.splitext(f)[1].lower() in allowed
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    base = path.rstrip('/').rstrip('\\')
    urls = [f"/media/file?path={base}/{f}" for f in files]
    return {"path": path, "files": urls}


def lexical_resolve(path):
    if os.path.isabs(path):
        return os.path.normpath(path)
    joined = os.path.normpath(os.path.join(PROJECT_ROOT, path))
    if joined != PROJECT_ROOT and not joined.startswith(PROJECT_ROOT + os.sep):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid path")
    return joined


@router.get("/folders")
async def list_folders(path: str):
    resolved = lexical_resolve(path)

    if not os.path.isdir(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"directory not found: {path}")

    try:
        folders = sorted(
            entry for entry in os.listdir(resolved)
            if os.path.isdir(os.path.join(resolved, entry)) and not entry.startswith('.')
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    return {"path": path, "folders": folders}


@router.get("/file")
async def serve_file(path: str):
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path is not a file")

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported file type")

    media_type, _ = mimetypes.guess_type(resolved)
    return FileResponse(resolved, media_type=media_type or "application/octet-stream")


@router.get("/json")
async def serve_json(path: str):
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path is not a file")

    if os.path.splitext(resolved)[1].lower() != '.json':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported file type")

    # holds the api key and other secrets
    if resolved == os.path.realpath(os.path.join(PROJECT_ROOT, 'confs', 'main_config.json')):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="main_config.json is not served")

    return FileResponse(resolved, media_type="application/json")


@router.get("/list_videos")
async def list_videos():
    if not os.path.isdir(GUIDE_VIDEOS_DIR):
        return {"files": []}
    try:
        files = sorted(
            f for f in os.listdir(GUIDE_VIDEOS_DIR)
            if os.path.isfile(os.path.join(GUIDE_VIDEOS_DIR, f))
            and os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    return {"files": [f"/guide_videos/{f}" for f in files]}