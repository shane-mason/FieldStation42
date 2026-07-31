from fastapi import APIRouter
from datetime import datetime
from pathlib import Path
import re
from fs42.station_manager import StationManager
from fs42.liquid_api import LiquidAPI
from fs42.metadata_io import MetadataIO
from fs42.title_parser import TitleParser

router = APIRouter(prefix="/schedules", tags=["schedules"])
EPISODE_RE = re.compile(
    r"(?i)^(?P<series>.*?)[\s._-]*s(?P<season>\d{1,3})"
    r"[\s._-]*e(?P<episode>\d{1,3}[a-z]*)[\s._-]*(?P<title>.*)$"
)
SEASON_DIR_RE = re.compile(r"(?i)^season[\s._-]*\d+$|^s\d+$")
MOVIE_YEAR_RE = re.compile(
    r"^(?P<title>.+?)[\s._-]+(?:\()?(?P<year>(?:19|20)\d{2})(?:\))?"
    r"(?:[\s._-]+.*)?$"
)
TITLE_ALIASES = {
    "shingeki no kyojin": "Attack on Titan",
}


def _guide_title_alias(title: str) -> str:
    normalized = TitleParser.parse_title(title)
    lowered = normalized.casefold()
    for source, replacement in TITLE_ALIASES.items():
        if lowered == source or lowered.startswith(source + " "):
            return replacement
    return normalized


def _movie_display(path: str) -> dict:
    media_path = Path(path)
    # Movie libraries commonly place featurettes and documentaries beneath a
    # "Movie Name (Year)" directory. Never let those auxiliary filenames
    # replace the identity of the movie in an already-generated schedule.
    candidates = [media_path.stem, *(parent.name for parent in media_path.parents[:3])]
    for candidate in candidates:
        match = MOVIE_YEAR_RE.match(candidate)
        if match:
            return {
                "display_title": (
                    f"{TitleParser.parse_title(match.group('title'))} "
                    f"({match.group('year')})"
                )
            }
    return {}


def _episode_display(path: str, meta: dict | None = None) -> dict:
    """Return stable series and episode labels without changing stored titles."""
    meta = meta or {}
    filename = Path(path).stem
    match = EPISODE_RE.match(filename)
    if meta.get("type") != "episode" and not match:
        return {}

    series_title = meta.get("show_title")
    episode_title = meta.get("title")
    season = meta.get("season")
    episode = meta.get("episode")

    if match:
        series_prefix = match.group("series").strip(" ._-")
        if not series_title and series_prefix:
            series_title = TitleParser.parse_title(series_prefix)
        if not episode_title and match.group("title"):
            episode_title = TitleParser.parse_title(match.group("title"))
        season = season if season is not None else int(match.group("season"))
        episode = episode if episode is not None else match.group("episode")

    if not series_title:
        parent = Path(path).parent
        if SEASON_DIR_RE.match(parent.name):
            parent = parent.parent
        if parent.name:
            series_title = TitleParser.parse_title(parent.name)

    result = {
        "display_title": _guide_title_alias(
            series_title or TitleParser.parse_title(filename)
        ),
        "episode_title": episode_title or "",
        "season": season,
        "episode": episode,
    }
    return result


def _attach_meta(blocks, read_meta: bool = True):
    """Attach cached NFO/tag metadata to each single-content block in place.

    Multi-content blocks (clip shows, loops) and off-air blocks have no single
    feature to describe, so they are left without a `meta` field and consumers
    fall back to the block title.
    """
    if not blocks:
        return blocks
    for block in blocks:
        content = getattr(block, "content", None)
        if content is None or isinstance(content, list):
            continue
        path = getattr(content, "path", None)
        if not path:
            continue
        meta = MetadataIO.read(path) if read_meta else None
        if meta:
            block.meta = meta
        display = _episode_display(path, meta) or _movie_display(path)
        if not display:
            aliased = _guide_title_alias(getattr(block, "title", ""))
            if aliased != getattr(block, "title", ""):
                display = {"display_title": aliased}
        for key, value in display.items():
            setattr(block, key, value)
    return blocks

@router.get("/search_all")
async def search_all_schedules(query: str = None):
    if not query:
        # If no query, get all blocks from all stations
        station_manager = StationManager()
        all_results = []
        
        for station in station_manager.stations:
            if station.get("_has_schedule", False):
                try:
                    schedule_blocks = LiquidAPI.get_blocks(station)
                    if schedule_blocks:
                        all_results.append({
                            "network_name": station["network_name"],
                            "schedule_blocks": schedule_blocks
                        })
                except Exception as e:
                    all_results.append({
                        "network_name": station["network_name"],
                        "error": str(e),
                        "schedule_blocks": []
                    })
        
        return {"query": query, "results": all_results}
    else:
        # Search across all stations at once
        try:
            search_results = LiquidAPI.search_all_blocks(query)
            all_results = []
            
            for station_name, blocks in search_results.items():
                if blocks:
                    all_results.append({
                        "network_name": station_name,
                        "schedule_blocks": blocks
                    })
            
            return {"query": query, "results": all_results}
        except Exception as e:
            return {"query": query, "error": str(e), "results": []}

@router.get("/search/{network_name}")
async def search_schedule(network_name: str, query: str = None):
    conf = StationManager().station_by_name(network_name)
    if query:
        schedule_blocks = LiquidAPI.search_blocks(conf, query)
    else:
        schedule_blocks = LiquidAPI.get_blocks(conf)

    return {"network_name": network_name, "query": query, "schedule_blocks": schedule_blocks}

@router.get("/{network_name}")
async def get_schedule(
    network_name: str,
    start: str = None,
    end: str = None,
    include_meta: bool = False,
    include_display: bool = False,
):
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
    if include_meta or include_display:
        _attach_meta(schedule_blocks, read_meta=include_meta)
    return {"network_name": network_name, "schedule_blocks": schedule_blocks}
