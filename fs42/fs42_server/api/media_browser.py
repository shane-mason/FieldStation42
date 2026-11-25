import logging
import mimetypes
import os
import re
import subprocess
from functools import lru_cache
from html.parser import HTMLParser
from math import isfinite
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from requests import RequestException

from fs42.nfo_agent import NFOAgent
from fs42.station_manager import StationManager
from .tmdb_helper import TMDB_MOVIE_GENRES, get_tmdb_helper
from . import tvmaze_helper


router = APIRouter(prefix="/media-browser", tags=["media-browser"])

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def configured_libraries(station):
    """Normalize the movie/show rows declared in station_conf.media_browser."""
    config = station.get("media_browser")
    if not isinstance(config, dict):
        return []

    libraries = []
    for kind, default_title in (("movies", "Movies"), ("shows", "TV Shows")):
        entries = config.get(kind, [])
        if isinstance(entries, (str, dict)):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, str):
                path = entry
                title = default_title
            elif isinstance(entry, dict):
                path = entry.get("path")
                title = entry.get("title") or default_title
            else:
                continue
            if isinstance(path, str) and path.strip():
                libraries.append(
                    {
                        "id": f"{kind}-{index}",
                        "kind": kind,
                        "title": str(title),
                        "path": path,
                    }
                )
    return libraries


def station_media_roots(station):
    roots = []
    content_dir = station.get("content_dir")
    if isinstance(content_dir, str) and content_dir.strip():
        roots.append(content_dir)
    roots.extend(library["path"] for library in configured_libraries(station))
    return roots


def _is_video_file(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def _read_nfo(path):
    metadata = NFOAgent.read_metadata_from_disk(path)
    fields = NFOAgent.display_fields(metadata) if metadata else None
    return metadata or {}, fields or {}


def _read_tvshow_nfo(directory):
    path = os.path.join(directory, "tvshow.nfo")
    try:
        with open(path, "r", encoding="utf-8") as file:
            metadata = NFOAgent.parse_nfo_string(file.read()) or {}
    except OSError:
        metadata = {}
    return metadata if metadata.get("type") == "tvshow" else {}


def _find_sidecar_image(path):
    base_path = os.path.splitext(path)[0]
    for extension in IMAGE_EXTENSIONS:
        candidate = base_path + extension
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_directory_image(directory):
    directory_name = os.path.basename(os.path.normpath(directory))
    for stem in ("poster", "folder", directory_name):
        for extension in IMAGE_EXTENSIONS:
            candidate = os.path.join(directory, stem + extension)
            if os.path.isfile(candidate):
                return candidate
    return None


def _art_url(channel_number, library, image_path):
    if not image_path:
        return None
    relative = os.path.relpath(image_path, library["path"]).replace(os.sep, "/")
    return f"/media-browser/{channel_number}/art/{library['id']}/{quote(relative, safe='/')}"


def _media_item(path, channel_number, library, fallback_title=None):
    metadata, fields = _read_nfo(path)
    filename_title = os.path.splitext(os.path.basename(path))[0]
    image_url = _art_url(channel_number, library, _find_sidecar_image(path))
    title = fields.get("title") or fallback_title or filename_title
    genres = metadata.get("genre", [])
    if isinstance(genres, str):
        genres = [genres]
    return {
        "type": metadata.get("type", "movie"),
        "title": title,
        "info": fields.get("info", ""),
        "description": fields.get("description", ""),
        "year": metadata.get("year", ""),
        "genres": genres,
        "content_rating": NFOAgent.normalize_content_rating(metadata.get("content_rating")),
        "video_path": path,
        "image_url": image_url,
        "tmdb_query": filename_title,
        "modified_at": os.path.getmtime(path),
    }


def scan_movie_library(channel_number, library):
    items = []
    for directory, _, filenames in os.walk(library["path"], followlinks=True):
        for filename in sorted(filenames):
            path = os.path.join(directory, filename)
            if _is_video_file(path):
                items.append(_media_item(path, channel_number, library))
    return sorted(items, key=lambda item: item["title"].casefold())


def _episode_numbers(metadata, path):
    season = metadata.get("season")
    episode = metadata.get("episode")
    match = re.search(r"[Ss](\d{1,3})[Ee](\d{1,3})", os.path.basename(path))
    if match:
        season = season if isinstance(season, int) else int(match.group(1))
        episode = episode if isinstance(episode, int) else int(match.group(2))
    if not isinstance(season, int):
        for part in reversed(os.path.normpath(path).split(os.sep)):
            season_match = re.match(r"season\s*(\d+)", part, re.IGNORECASE)
            if season_match:
                season = int(season_match.group(1))
                break
    return season if isinstance(season, int) else 0, episode if isinstance(episode, int) else 0


def _episode_title_from_filename(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    normalized = re.fullmatch(r".+ \(\d{4}\) - S\d{1,3}E\d{1,3}(?:(?:-E|E)\d{1,3})* - (.+)", stem, re.I)
    return normalized[1] if normalized else stem


def _scan_show_directory(channel_number, library, show_directory, loose_files=None):
    show_metadata = _read_tvshow_nfo(show_directory)
    show_title = show_metadata.get("title") or os.path.basename(os.path.normpath(show_directory))
    show_year = str(show_metadata.get("year") or "")
    if re.fullmatch(r"\d{4}", show_year) and not re.search(r"\(\d{4}\)$", show_title):
        tvmaze_show_query = f"{show_title} ({show_year})"
    else:
        tvmaze_show_query = show_title
    tvmaze_id_query = tvmaze_helper.show_id_query(show_metadata)
    episode_paths = list(loose_files or [])
    if not loose_files:
        for directory, _, filenames in os.walk(show_directory, followlinks=True):
            episode_paths.extend(
                os.path.join(directory, filename)
                for filename in filenames
                if _is_video_file(filename)
            )

    seasons = {}
    latest = 0
    first_episode_image = None
    for path in episode_paths:
        metadata, fields = _read_nfo(path)
        season_number, episode_number = _episode_numbers(metadata, path)
        episode_item = _media_item(path, channel_number, library)
        relative_path = quote(os.path.relpath(path, library["path"]).replace(os.sep, "/"), safe="/")
        media_url = f"{library['id']}/{relative_path}"
        series = metadata.get("show_title") or show_title
        filename_series = re.match(r"(.+ \(\d{4}\)) - S\d{1,3}E\d{1,3}(?:(?:-E|E)\d{1,3})*(?: - |\.)", os.path.basename(path), re.I)
        episode_item.update(
            {
                "type": "episode",
                "show_title": series,
                "tvmaze_query": tvmaze_id_query or (filename_series[1] if filename_series else tvmaze_show_query if not loose_files else series),
                "season": season_number,
                "episode": episode_number,
                "title": fields.get("title") or _episode_title_from_filename(path),
                "runtime_url": f"/media-browser/{channel_number}/runtime/{media_url}",
                "screenshot_url": f"/media-browser/{channel_number}/screenshot/{media_url}",
            }
        )
        seasons.setdefault(season_number, []).append(episode_item)
        latest = max(latest, episode_item["modified_at"])
        first_episode_image = first_episode_image or _find_sidecar_image(path)

    season_list = []
    for number, episodes in sorted(seasons.items()):
        episodes.sort(key=lambda item: (item["episode"], item["title"].casefold()))
        season_list.append(
            {
                "number": number,
                "title": "Specials" if number == 0 else f"Season {number}",
                "episodes": episodes,
            }
        )

    genres = show_metadata.get("genre", [])
    if isinstance(genres, str):
        genres = [genres]
    return {
        "type": "show",
        "title": show_title,
        "info": str(show_metadata.get("year", "")),
        "description": show_metadata.get("plot", ""),
        "year": show_metadata.get("year", ""),
        "genres": genres,
        "content_rating": NFOAgent.normalize_content_rating(show_metadata.get("content_rating")),
        "image_url": _art_url(
            channel_number,
            library,
            _find_directory_image(show_directory) or first_episode_image,
        ),
        "modified_at": latest,
        "seasons": season_list,
    }


def scan_show_library(channel_number, library):
    try:
        entries = sorted(os.scandir(library["path"]), key=lambda entry: entry.name.casefold())
    except OSError:
        return []

    shows = []
    loose_by_title = {}
    for entry in entries:
        if entry.is_dir(follow_symlinks=True):
            show = _scan_show_directory(channel_number, library, entry.path)
            if show["seasons"]:
                shows.append(show)
        elif entry.is_file(follow_symlinks=True) and _is_video_file(entry.name):
            metadata, _ = _read_nfo(entry.path)
            title = metadata.get("show_title") or "Other"
            loose_by_title.setdefault(title, []).append(entry.path)
    for title, paths in loose_by_title.items():
        show = _scan_show_directory(channel_number, library, library["path"], paths)
        show["title"] = title
        if show["seasons"]:
            shows.append(show)
    return sorted(shows, key=lambda item: item["title"].casefold())


@router.get("/{channel_number}")
async def get_catalog(channel_number: int):
    """Build the configured movie rows and television season/episode hierarchy."""
    station = StationManager().station_by_channel(channel_number)
    if station is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_number} not found")

    libraries = configured_libraries(station)
    if not libraries:
        raise HTTPException(
            status_code=400,
            detail="This station does not define station_conf.media_browser movies or shows",
        )

    rows = []
    for library in libraries:
        if not os.path.isdir(library["path"]):
            logging.getLogger("MEDIA_BROWSER_API").warning(
                "Skipping missing media browser directory: %s", library["path"]
            )
            continue
        items = (
            scan_movie_library(channel_number, library)
            if library["kind"] == "movies"
            else scan_show_library(channel_number, library)
        )
        if items:
            rows.append(
                {
                    "id": library["id"],
                    "kind": library["kind"],
                    "title": library["title"],
                    "items": items,
                }
            )

    return {
        "channel_number": channel_number,
        "network_name": station.get("network_name", f"Channel {channel_number}"),
        "tmdb_movie_genres": sorted(set(TMDB_MOVIE_GENRES.values())),
        "rows": rows,
    }


@router.get("/{channel_number}/art/{library_id}/{image_path:path}")
async def get_art(channel_number: int, library_id: str, image_path: str):
    """Serve artwork below one of the station's explicitly configured library roots."""
    station = StationManager().station_by_channel(channel_number)
    library = next(
        (entry for entry in configured_libraries(station or {}) if entry["id"] == library_id),
        None,
    )
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")

    root = os.path.abspath(os.path.normpath(library["path"]))
    candidate = os.path.abspath(os.path.normpath(os.path.join(root, image_path)))
    try:
        is_inside_library = os.path.commonpath((root, candidate)) == root
    except ValueError:
        is_inside_library = False
    if not is_inside_library or not os.path.isfile(candidate):
        raise HTTPException(status_code=404, detail="Artwork not found")

    extension = os.path.splitext(candidate)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported artwork type")
    media_type, _ = mimetypes.guess_type(candidate)
    return FileResponse(
        candidate,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@lru_cache(maxsize=2048)
def _runtime_minutes(path, modified_ns, size):
    # The file modification time and size invalidate cached results on replacement.
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file",
             "-format_whitelist", "mov,matroska,avi,asf,flv", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True, timeout=5,
        )
        seconds = float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return max(1, int(seconds / 60 + 0.5)) if isfinite(seconds) and seconds > 0 else None


def _episode_video_path(channel_number, library_id, video_path):
    station = StationManager().station_by_channel(channel_number)
    library = next((entry for entry in configured_libraries(station or {})
                    if entry["id"] == library_id and entry["kind"] == "shows"), None)
    if library is None:
        raise HTTPException(status_code=404, detail="Show library not found")

    root = os.path.abspath(library["path"])
    candidate = os.path.abspath(os.path.join(root, video_path))
    try:
        is_inside_library = os.path.commonpath((root, candidate)) == root
    except ValueError:
        is_inside_library = False
    if not is_inside_library or not _is_video_file(candidate) or not os.path.isfile(candidate):
        raise HTTPException(status_code=404, detail="Episode not found")
    return candidate


@router.get("/{channel_number}/runtime/{library_id}/{video_path:path}")
def get_episode_runtime(channel_number: int, library_id: str, video_path: str):
    candidate = _episode_video_path(channel_number, library_id, video_path)
    try:
        stat = os.stat(candidate)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Episode not found") from exc
    return {"minutes": _runtime_minutes(candidate, stat.st_mtime_ns, stat.st_size)}


@lru_cache(maxsize=128)
def _episode_screenshot(path, modified_ns, size):
    try:
        for position in (30, 0):
            result = subprocess.run(
                ["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file",
                 "-format_whitelist", "mov,matroska,avi,asf,flv", "-ss", str(position),
                 "-i", path, "-map", "0:V:0", "-frames:v", "1",
                 "-vf", "scale=640:360:force_original_aspect_ratio=decrease",
                 "-c:v", "mjpeg", "-f", "image2pipe", "pipe:1"],
                capture_output=True, check=True, timeout=5,
            )
            if result.stdout:
                return result.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return None


@router.get("/{channel_number}/screenshot/{library_id}/{video_path:path}")
def get_episode_screenshot(channel_number: int, library_id: str, video_path: str):
    candidate = _episode_video_path(channel_number, library_id, video_path)
    try:
        stat = os.stat(candidate)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Episode not found") from exc
    jpeg = _episode_screenshot(candidate, stat.st_mtime_ns, stat.st_size)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="Episode screenshot unavailable")
    return Response(jpeg, media_type="image/jpeg")


def _tvmaze_summary_text(summary):
    parts = []

    class SummaryParser(HTMLParser):
        def handle_data(self, data):
            parts.append(data)

        def handle_starttag(self, tag, attrs):
            if tag in {"p", "br", "div", "li"}:
                parts.append(" ")

    SummaryParser().feed(summary or "")
    return " ".join("".join(parts).split())


@router.get("/{channel_number}/episode-metadata")
def get_episode_metadata(channel_number: int, show: str, season: int, number: int):
    manager = StationManager()
    if manager.station_by_channel(channel_number) is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_number} not found")
    if not show.strip() or len(show) > 300 or not 0 <= season <= 999 or not 1 <= number <= 999:
        raise HTTPException(status_code=400, detail="A valid show, season and episode number are required")

    try:
        matches = tvmaze_helper.search_shows(show.strip())
        episode = tvmaze_helper.get_episode(
            matches[0], season, number, manager.server_conf, include_metadata=True,
        ) if len(matches) == 1 else None
    except tvmaze_helper.EpisodeOrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Episode provider lookup failed") from exc
    if not episode:
        raise HTTPException(status_code=404, detail="No unique TVmaze episode match")

    image = episode.get("image") or {}
    image_url = image.get("original") or image.get("medium")
    return {
        "description": _tvmaze_summary_text(episode.get("summary")),
        "image_url": image_url if image_url and image_url.startswith("https://static.tvmaze.com/") else None,
        "source_url": f"https://www.tvmaze.com/episodes/{episode['id']}" if episode.get("id") else None,
    }


@router.get("/{channel_number}/tmdb")
def get_tmdb_metadata(channel_number: int, title: str):
    """Return one movie's TMDB data without blocking the initial catalog response."""
    if StationManager().station_by_channel(channel_number) is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_number} not found")
    if not title.strip() or len(title) > 300:
        raise HTTPException(status_code=400, detail="A valid movie title is required")

    helper = get_tmdb_helper()
    if not helper.is_configured():
        return {"configured": False, "movie": None}
    return {"configured": True, "movie": helper.search_movie(title.strip())}
