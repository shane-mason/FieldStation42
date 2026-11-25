from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import logging
import mimetypes
from urllib.parse import urlparse
from fs42.station_manager import StationManager
from fs42.nfo_agent import NFOAgent
from .tmdb_helper import get_tmdb_helper
from .player import connected_command_queue, send_web_key
from .media_browser import station_media_roots

router = APIRouter(prefix="/ppv", tags=["ppv"])

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}

# Pydantic Models
class NFOData(BaseModel):
    """NFO file content: title, info line, description"""
    title: str
    info: str
    description: str

class PPVContent(BaseModel):
    """A single PPV content item with video and metadata"""
    filename: str
    video_path: str
    nfo: Optional[NFOData] = None
    has_nfo: bool
    has_image: bool
    image_url: Optional[str] = None
    modified_at: float

class PPVContentListResponse(BaseModel):
    """Response containing list of PPV content"""
    channel_number: int
    network_name: str
    content_dir: str
    content_count: int
    contents: List[PPVContent]

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[str] = None

class PlayFileRequest(BaseModel):
    """Request to play a file"""
    file_path: str

class PlayFileResponse(BaseModel):
    """Response from play_file endpoint"""
    success: bool
    message: str


@router.get("/{channel_number}", response_model=PPVContentListResponse)
async def get_ppv_content(channel_number: int, variation: Optional[str] = None):
    """
    Get PPV content for a specific channel.
    Reads the content_dir from the station config and returns all video files with their NFO metadata.

    Args:
        channel_number: The channel number to get PPV content for
        variation: Optional variation parameter (for future use, similar to bump variations)
    """
    logger = logging.getLogger("PPV_API")

    # Get station configuration
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_number} not found"
        )

    # Get content_dir from station config
    content_dir = station.get("content_dir")
    if not content_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Channel {channel_number} does not have a content_dir configured"
        )

    # Check if content_dir exists
    if not os.path.exists(content_dir):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Content directory '{content_dir}' not found"
        )

    if not os.path.isdir(content_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content path '{content_dir}' is not a directory"
        )

    # Read directory contents
    try:
        contents = []
        for filename in sorted(os.listdir(content_dir)):
            file_path = os.path.join(content_dir, filename)

            # Skip directories
            if os.path.isdir(file_path):
                continue

            # Get file extension
            _, ext = os.path.splitext(filename)

            # Only process video files
            if ext.lower() in VIDEO_EXTENSIONS:
                base_path = os.path.splitext(file_path)[0]
                base_name = os.path.splitext(filename)[0]

                # Look for corresponding NFO file
                nfo_data = None
                has_nfo = False

                file_meta = NFOAgent.read_metadata_from_disk(file_path)
                if file_meta:
                    fields = NFOAgent.display_fields(file_meta)
                    nfo_data = NFOData(
                        title=fields["title"],
                        info=fields["info"],
                        description=fields["description"],
                    )
                    has_nfo = True

                # Look for corresponding image file (jpg, jpeg, png)
                image_url = None
                has_image = False
                image_extensions = ['.jpg', '.jpeg', '.png']

                for img_ext in image_extensions:
                    img_path = base_path + img_ext
                    if os.path.exists(img_path):
                        # Create URL for image endpoint
                        image_url = f"/ppv/image/{channel_number}/{base_name}{img_ext}"
                        has_image = True
                        break

                # If no NFO or no image, try TMDB
                tmdb_data = None
                if not has_nfo or not has_image:
                    tmdb_helper = get_tmdb_helper()
                    if tmdb_helper.is_configured():
                        # Pass the raw filename - TMDB helper will parse year and normalize
                        tmdb_data = tmdb_helper.search_movie(base_name)

                # Use TMDB data if no NFO
                if not has_nfo:
                    if tmdb_data:
                        nfo_data = NFOData(
                            title=tmdb_data.get("title", base_name),
                            info=tmdb_data.get("release_date", "")[:4] if tmdb_data.get("release_date") else "",
                            description=tmdb_data.get("overview", "")
                        )
                        logger.info(f"Using TMDB metadata for {base_name}")
                    else:
                        nfo_data = NFOData(
                            title=base_name,
                            info="",
                            description=""
                        )

                # Use TMDB poster if no local image
                if not has_image and tmdb_data and tmdb_data.get("poster_url"):
                    image_url = tmdb_data["poster_url"]
                    has_image = True
                    logger.info(f"Using TMDB poster for {base_name}")

                contents.append(PPVContent(
                    filename=filename,
                    video_path=file_path,
                    nfo=nfo_data,
                    has_nfo=has_nfo,
                    has_image=has_image,
                    image_url=image_url,
                    modified_at=os.path.getmtime(file_path),
                ))

        return PPVContentListResponse(
            channel_number=channel_number,
            network_name=station.get("network_name", "Unknown"),
            content_dir=content_dir,
            content_count=len(contents),
            contents=contents
        )

    except Exception as e:
        logger.error(f"Error reading content directory {content_dir}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read content directory: {str(e)}"
        )


@router.get("/image/{channel_number}/{filename}")
async def get_ppv_image(channel_number: int, filename: str):
    """
    Serve an image file from a channel's content_dir.

    Args:
        channel_number: The channel number
        filename: The image filename (e.g., "movie.jpg")
    """
    logger = logging.getLogger("PPV_API")

    # Get station configuration
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_number} not found"
        )

    # Get content_dir from station config
    content_dir = station.get("content_dir")
    if not content_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Channel {channel_number} does not have a content_dir configured"
        )

    # Security: Only allow image files
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    _, ext = os.path.splitext(filename)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed"
        )

    # Security: Prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )

    # Build full path
    image_path = os.path.join(content_dir, filename)

    # Check if file exists
    if not os.path.exists(image_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image '{filename}' not found"
        )

    # Check if it's a file (not a directory)
    if not os.path.isfile(image_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a file"
        )

    # Determine media type
    media_type, _ = mimetypes.guess_type(image_path)
    if media_type is None:
        media_type = "application/octet-stream"

    # Return the image file
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=3600"  # Cache for 1 hour
        }
    )


@router.post("/{channel_number}/play_file", response_model=PlayFileResponse)
async def play_file(channel_number: int, play_request: PlayFileRequest, request: Request):
    """
    Play a file by sending a command to the player via the command queue.

    Args:
        channel_number: The channel number (for validation)
        play_request: PlayFileRequest containing the file path
        request: FastAPI Request object (to access app state)
    """
    logger = logging.getLogger("PPV_API")

    # Get station configuration to validate channel exists
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_number} not found"
        )

    # Validate that the file exists
    if not os.path.exists(play_request.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {play_request.file_path}"
        )

    command_queue = connected_command_queue(request)

    # Create the command to send to the player
    command = {
        "command": "play_file",
        "file_path": play_request.file_path,
        "channel_number": channel_number,
    }

    try:
        logger.info(f"Sending play command for file: {play_request.file_path}")

        # Put the command in the queue
        command_queue.put(command)

        logger.info(f"Successfully queued play command for: {play_request.file_path}")

        return PlayFileResponse(
            success=True,
            message=f"Play command sent for: {os.path.basename(play_request.file_path)}"
        )

    except Exception as e:
        logger.error(f"Error sending play command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send play command: {str(e)}"
        )

@router.post("/{channel_number}/key/{key_name}", deprecated=True)
async def send_key(channel_number: int, key_name: str, request: Request):
    """Deprecated alias for POST /player/web/key/{key_name}."""
    return await send_web_key(key_name, request)


@router.post("/{channel_number}/control/{action}")
async def control_ppv(channel_number: int, action: str, request: Request):
    """Navigate the active PPV list or control its playing video."""
    if action not in {"rewind", "play", "pause", "stop", "fastForward"}:
        raise HTTPException(status_code=400, detail="Action must be rewind, play, pause, stop, or fastForward")

    station = StationManager().station_by_channel(channel_number)
    web_path = urlparse((station or {}).get("web_url", "")).path.rstrip("/")
    ppv_pages = (
        "/static/ppv/ppv.html",
        "/static/ppv/ppv_list.html",
        "/static/media_browser/myflix.html",
    )
    if (
        not station
        or station.get("network_type") != "web"
        or not station_media_roots(station)
        or not web_path.endswith(ppv_pages)
    ):
        raise HTTPException(status_code=400, detail=f"Channel {channel_number} is not a PPV channel")

    status_path = StationManager().server_conf.get("status_socket")
    try:
        with open(status_path, "r") as status_file:
            player_status = json.load(status_file)
        active_channel = int(player_status.get("channel_number"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        active_channel = None
        player_status = {}

    if player_status.get("status") != "playing" or active_channel != channel_number:
        raise HTTPException(status_code=409, detail="The PPV channel is not currently playing")

    video_path = player_status.get("file_path")
    is_video = False
    if video_path:
        # Compare normalized paths without resolving symlinks: catalog entries may
        # point to media outside the catalog through symlinked files/directories.
        video_path = os.path.abspath(os.path.normpath(video_path))
        is_under_content = False
        for configured_root in station_media_roots(station):
            content_dir = os.path.abspath(os.path.normpath(configured_root))
            try:
                if os.path.commonpath((content_dir, video_path)) == content_dir:
                    is_under_content = True
                    break
            except ValueError:
                continue
        is_video = (
            is_under_content
            and os.path.splitext(video_path)[1].lower() in VIDEO_EXTENSIONS
        )

    command_queue = connected_command_queue(request)
    if is_video:
        mpv_actions = {
            "rewind": "ppv_backward",
            "play": "ppv_play",
            "pause": "ppv_pause",
            "stop": "ppv_stop",
            "fastForward": "ppv_forward",
        }
        command_queue.put({"command": "mpv_command", "action": mpv_actions[action]})
        return {"status": "ok", "action": action, "mode": "video"}

    if action in {"pause", "stop"}:
        raise HTTPException(status_code=409, detail=f"{action.title()} is available while a PPV movie is playing")

    web_keys = {"rewind": "PageUp", "play": "Enter", "fastForward": "PageDown"}
    command_queue.put({"command": "web_key", "key": web_keys[action]})
    return {"status": "ok", "action": action, "mode": "list"}
