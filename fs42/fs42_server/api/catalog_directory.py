import ctypes
import errno
import hmac
import json
import os
import re
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from difflib import SequenceMatcher
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from requests import RequestException

from fs42.fs42_server.api.media import AUDIO_EXTENSIONS, PROJECT_ROOT, VIDEO_EXTENSIONS
from fs42.nfo_agent import NFOAgent
from fs42.station_manager import StationManager
from .tmdb_helper import get_tmdb_helper
from . import tvmaze_helper

router = APIRouter(prefix="/catalog-directory", tags=["catalog-directory"])

CATALOG_ROOT = os.path.realpath(os.path.join(PROJECT_ROOT, "catalog"))
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
METADATA_EXTENSIONS = {".nfo", ".jpg", ".jpeg", ".png", ".webp"}
PSEUDO_FILESYSTEMS = {
    "autofs", "bpf", "cgroup", "cgroup2", "configfs", "debugfs", "devpts",
    "devtmpfs", "efivarfs", "fusectl", "mqueue", "overlay", "proc", "pstore",
    "securityfs", "sysfs", "tracefs", "tmpfs",
}
NETWORK_FILESYSTEMS = {"9p", "cifs", "fuse.sshfs", "nfs", "nfs4", "smb3"}
EXCLUDED_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/boot")
NORMALIZATION_KEY = os.urandom(32)
NORMALIZATION_LOCK = Lock()


class CreateDirectoryRequest(BaseModel):
    path: str = ""
    name: str


class CreateLinkRequest(BaseModel):
    mount: str
    source_path: str
    catalog_path: str = ""
    link_name: str | None = None


class RenameEntryRequest(BaseModel):
    path: str
    new_name: str


class RenameSourceRequest(RenameEntryRequest):
    mount: str


class DeleteEntryRequest(BaseModel):
    path: str


class CatalogLink(BaseModel):
    path: str
    target: str


class ImportCatalogLinksRequest(BaseModel):
    version: int = 1
    links: list[CatalogLink]


class DriveCatalogFileRequest(BaseModel):
    mount: str
    path: str = ""
    filename: str


class CheckTMDBRequest(BaseModel):
    mount: str
    path: str


class NormalizeTMDBRequest(CheckTMDBRequest):
    name: str
    token: str


def _inside(path, root):
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(root))) == os.path.realpath(root)
    except ValueError:
        return False


def _relative_path(value):
    if not isinstance(value, str) or "\0" in value:
        raise HTTPException(status_code=400, detail="Invalid relative path.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise HTTPException(status_code=400, detail="Path must stay inside its selected root.")
    return os.path.join(*path.parts) if path.parts else ""


def _catalog_directory(relative_path):
    os.makedirs(CATALOG_ROOT, exist_ok=True)
    relative_path = _relative_path(relative_path)
    candidate = os.path.abspath(os.path.join(CATALOG_ROOT, relative_path))
    if not _inside(candidate, CATALOG_ROOT):
        raise HTTPException(status_code=400, detail="Path must stay inside catalog/.")
    if not os.path.isdir(candidate):
        raise HTTPException(status_code=404, detail="Catalog directory not found.")
    return candidate


def _catalog_entry(relative_path):
    relative_path = _relative_path(relative_path)
    if not relative_path:
        raise HTTPException(status_code=400, detail="The catalog root cannot be renamed or removed.")
    candidate = os.path.abspath(os.path.join(CATALOG_ROOT, relative_path))
    parent = os.path.dirname(candidate)
    if not _inside(parent, CATALOG_ROOT):
        raise HTTPException(status_code=400, detail="Entry must stay inside catalog/.")
    if not os.path.lexists(candidate):
        raise HTTPException(status_code=404, detail="Catalog entry not found.")
    return candidate


def _mounts():
    mounts = {}
    try:
        with open("/proc/self/mounts", encoding="utf-8") as fp:
            records = fp.readlines()
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Mounted drives are unavailable: {exc}")

    for record in records:
        fields = record.split()
        if len(fields) < 3:
            continue
        source, raw_target, filesystem = fields[:3]
        target = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), raw_target)
        target = os.path.realpath(target)
        if target == "/" or not os.path.isdir(target) or filesystem in PSEUDO_FILESYSTEMS:
            continue
        if any(target == prefix or target.startswith(prefix + os.sep) for prefix in EXCLUDED_MOUNT_PREFIXES):
            continue
        common_media_path = any(
            target == prefix or target.startswith(prefix + os.sep)
            for prefix in ("/media", "/mnt", "/run/media")
        )
        is_device = source.startswith("/dev/")
        is_network = filesystem.lower() in NETWORK_FILESYSTEMS
        if not (common_media_path or is_device or is_network):
            continue
        mounts[target] = {
            "path": target,
            "label": os.path.basename(target.rstrip(os.sep)) or target,
            "source": source,
            "filesystem": filesystem,
        }
    return sorted(mounts.values(), key=lambda mount: mount["path"].lower())


def _selected_mount(mount_path):
    canonical = os.path.realpath(mount_path)
    for mount in _mounts():
        if mount["path"] == canonical:
            return canonical
    raise HTTPException(status_code=400, detail="Select a currently mounted drive.")


def _source_path(mount_path, relative_path):
    mount_root = _selected_mount(mount_path)
    relative_path = _relative_path(relative_path)
    candidate = os.path.realpath(os.path.join(mount_root, relative_path))
    if not _inside(candidate, mount_root):
        raise HTTPException(status_code=400, detail="Source path must stay on the selected drive.")
    return mount_root, candidate, relative_path


def _safe_name(name):
    if (
        not isinstance(name, str)
        or not name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\0" in name
    ):
        raise HTTPException(status_code=400, detail="Enter a valid name without slashes.")
    return name.strip()


@router.get("/drives")
async def list_mounted_drives():
    return {"drives": _mounts()}


@router.get("/source")
async def browse_source(mount: str, path: str = ""):
    mount_root, directory, relative_path = _source_path(mount, path)
    if not os.path.isdir(directory):
        raise HTTPException(status_code=404, detail="Source directory not found.")
    entries = []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if entry.name.startswith("."):
                    continue
                resolved = os.path.realpath(entry.path)
                if not _inside(resolved, mount_root):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=True):
                        entries.append({"name": entry.name, "type": "directory"})
                    elif (
                        entry.is_file(follow_symlinks=True)
                        and os.path.splitext(entry.name)[1].lower() in MEDIA_EXTENSIONS
                    ):
                        entries.append({"name": entry.name, "type": "media"})
                    elif entry.is_file(follow_symlinks=True) and entry.name.lower().endswith(".json"):
                        entries.append({"name": entry.name, "type": "catalog-export"})
                    elif entry.is_file(follow_symlinks=True):
                        extension = os.path.splitext(entry.name)[1].lower()
                        if extension in METADATA_EXTENSIONS:
                            entries.append(
                                {
                                    "name": entry.name,
                                    "type": "metadata",
                                    "kind": "nfo" if extension == ".nfo" else "artwork",
                                }
                            )
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while reading this drive.")
    entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].lower()))
    return {"path": relative_path.replace(os.sep, "/"), "entries": entries}


@router.get("/source/files")
def list_source_files(mount: str, path: str = ""):
    """List selectable media below a mounted-drive directory without following directory links."""
    mount_root, directory, relative_path = _source_path(mount, path)
    if not os.path.isdir(directory):
        raise HTTPException(status_code=404, detail="Source directory not found.")

    def raise_walk_error(error):
        raise error

    paths = []
    try:
        for current, directories, files in os.walk(directory, onerror=raise_walk_error):
            directories[:] = sorted(name for name in directories if not name.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or os.path.splitext(name)[1].lower() not in MEDIA_EXTENSIONS:
                    continue
                candidate = os.path.join(current, name)
                if _inside(candidate, mount_root) and os.path.isfile(candidate):
                    relative = os.path.join(relative_path, os.path.relpath(candidate, directory))
                    paths.append(relative.replace(os.sep, "/"))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied while scanning this folder.") from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail="Could not finish scanning this folder.") from exc
    return {"paths": paths}


@router.post("/tmdb/check")
def check_source_with_tmdb(request: CheckTMDBRequest):
    """Look up one mounted-drive file or directory without exposing the API key."""
    mount_root, source, relative_path = _source_path(request.mount, request.path)
    if not relative_path or not _inside(source, mount_root):
        raise HTTPException(
            status_code=400,
            detail="Choose a media file or directory on the mounted drive.",
        )
    if not os.path.isdir(source):
        raise HTTPException(
            status_code=400,
            detail="Choose a TV show directory on the mounted drive.",
        )

    name = os.path.basename(os.path.normpath(source))
    title = name
    helper = get_tmdb_helper()
    if not helper.is_configured():
        raise HTTPException(
            status_code=400,
            detail="TMDB is not configured. Add tmdb_api_key to confs/main_config.json.",
        )
    match = helper.search_media(title)
    if match is None:
        return {
            "path": relative_path.replace(os.sep, "/"),
            "query": title,
            "match": None,
            "files": None,
        }
    if match.get("media_type") != "tv":
        raise HTTPException(
            status_code=409,
            detail=f"TMDB matched '{match.get('title')}' as a movie, not a TV show.",
        )

    details = helper.get_tv_details(match["tmdb_id"])
    if not details:
        raise HTTPException(status_code=502, detail="Could not retrieve the TMDB TV show details.")
    poster_data = None
    poster_destination = os.path.join(source, "poster.jpg")
    if not os.path.exists(poster_destination):
        poster_data = helper.download_poster(details.get("poster_path"))
        if poster_data is None:
            raise HTTPException(status_code=502, detail="TMDB did not provide a downloadable show poster.")

    root = ET.Element("tvshow")

    def add_element(tag, value, attributes=None):
        if value in (None, ""):
            return
        element = ET.SubElement(root, tag, attributes or {})
        element.text = str(value)

    first_air_date = details.get("first_air_date") or ""
    add_element("title", details.get("name") or match.get("title"))
    add_element("originaltitle", details.get("original_name"))
    add_element("year", first_air_date[:4])
    add_element("premiered", first_air_date)
    add_element("plot", details.get("overview"))
    for genre in details.get("genres", []):
        if isinstance(genre, dict):
            add_element("genre", genre.get("name"))
    ratings = details.get("content_ratings", {}).get("results", [])
    us_rating = next(
        (
            rating.get("rating")
            for rating in ratings
            if rating.get("iso_3166_1") == "US" and rating.get("rating")
        ),
        "",
    )
    add_element("mpaa", us_rating)
    add_element("status", details.get("status"))
    for network in details.get("networks", []):
        if isinstance(network, dict):
            add_element("studio", network.get("name"))
    add_element("season", details.get("number_of_seasons"))
    add_element("episode", details.get("number_of_episodes"))
    add_element("rating", details.get("vote_average"))
    add_element("votes", details.get("vote_count"))
    add_element("uniqueid", details.get("id"), {"type": "tmdb", "default": "true"})
    nfo_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    nfo_destination = os.path.join(source, "tvshow.nfo")
    created = []
    existing = []
    try:
        if os.path.exists(nfo_destination):
            existing.append("tvshow.nfo")
        else:
            with open(nfo_destination, "xb") as fp:
                fp.write(nfo_data)
            created.append("tvshow.nfo")
        if os.path.exists(poster_destination):
            existing.append("poster.jpg")
        else:
            with open(poster_destination, "xb") as fp:
                fp.write(poster_data)
            created.append("poster.jpg")
    except FileExistsError as exc:
        existing.append(os.path.basename(exc.filename))
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied while writing {os.path.basename(exc.filename)}.",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write TV show metadata: {exc}") from exc

    return {
        "path": relative_path.replace(os.sep, "/"),
        "query": title,
        "match": match,
        "files": {"created": created, "existing": existing},
    }


def _mounted_rename_source(request, extensions):
    mount, source, relative = _source_path(request.mount, request.path)
    if not relative or source != os.path.join(mount, relative) or os.path.ismount(source):
        raise HTTPException(status_code=400, detail="Choose an item directly on the mounted drive, outside symlinked directories.")
    if os.path.isdir(source):
        return source, ""
    extension = os.path.splitext(source)[1]
    if os.path.isfile(source) and extension.lower() in extensions:
        return source, extension
    raise HTTPException(status_code=400, detail="Choose a folder or a supported file type.")


def _normalization_source(request):
    return _mounted_rename_source(request, VIDEO_EXTENSIONS)


def _normalization_token(source, name):
    try:
        stat = os.stat(source, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Selected item no longer exists.") from exc
    proposal = json.dumps([source, name, stat.st_dev, stat.st_ino]).encode()
    return hmac.new(NORMALIZATION_KEY, proposal, "sha256").hexdigest()


def _parse_episode_code(code):
    match = re.fullmatch(r"S(\d+)E(\d+)(.*)", code, re.I)
    if match:
        season, first, rest = match.groups()
        numbers = [int(first)]
        for separator, value in re.findall(r"(-E?|E)(\d+)", rest, re.I):
            last = int(value)
            if last <= numbers[-1]:
                raise HTTPException(status_code=400, detail="Episode numbers must be in increasing order.")
            if separator.startswith("-"):
                numbers.extend(range(numbers[-1] + 1, last + 1))
            else:
                numbers.append(last)
    elif code.isdecimal():
        season, numbers = int(code[:-2]), [int(code[-2:])]
    elif "." in code:
        season, number = map(int, code.split("."))
        numbers = [number]
    else:
        season, *numbers = map(int, re.split("x", code, flags=re.I))
        if numbers != sorted(set(numbers)):
            raise HTTPException(status_code=400, detail="Episode numbers must be in increasing order.")

    if len(numbers) > 30:
        raise HTTPException(status_code=400, detail="A single rename preview supports up to 30 episodes per file.")
    season = int(season)
    if len(numbers) > 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        formatted = f"S{season:02d}E{numbers[0]:02d}-E{numbers[-1]:02d}"
    else:
        formatted = f"S{season:02d}" + "".join(f"E{number:02d}" for number in numbers)
    return season, numbers, formatted


def _combined_episode_title(titles):
    if len(titles) == 1:
        return titles[0]
    parts = [re.sub(r"(?:\s*[-,:]?\s+Part\s+\d+|\s*\((?:Part\s+)?\d+\))$", "", title, flags=re.I).rstrip() for title in titles]
    if parts[0] and all(part.casefold() == parts[0].casefold() for part in parts):
        return parts[0]
    return " + ".join(dict.fromkeys(titles))


def _filename_episode_titles(stem, episode):
    title = stem[episode.end():].lstrip("] )-._")
    release_tag = re.search(
        r"[ ._-]+(?:\d{3,4}[pi]|web[ ._-]?(?:dl|rip)|blu[ ._-]?ray|hdtv|x26[45]|hevc)(?=$|[ ._-])",
        title, re.I,
    )
    if release_tag:
        title = title[:release_tag.start()]
    return [" ".join(part.replace(".", " ").replace("_", " ").split())
            for part in re.split(r"\.{2,}|\s+\+\s+", title) if part.strip()]


def _match_broadcast_segments(episodes, numbers, filename_titles):
    if len(numbers) != len(filename_titles) or not any("/" in (item.get("name") or "") for item in episodes):
        return None
    broadcast_episodes = sorted(
        (item for item in episodes if type(item.get("number")) is int and item["number"] > 0),
        key=lambda item: item["number"],
    )
    if [item["number"] for item in broadcast_episodes] != list(range(1, len(broadcast_episodes) + 1)):
        return None
    segments = [title.strip() for item in broadcast_episodes for title in (item.get("name") or "").split("/")]
    if not all(segments) or not all(1 <= number <= len(segments) for number in numbers):
        return None

    def key(title):
        return tvmaze_helper.title_key(re.sub(r"^the\s+", "", title, flags=re.I))

    def words_without_articles(title):
        return tuple(word for word in re.findall(r"\w+", title.casefold()) if word not in {"a", "an", "the", "of"})

    selected = [segments[number - 1] for number in numbers]
    for filename_title, selected_title in zip(filename_titles, selected):
        left, right = key(filename_title), key(selected_title)
        # A title variant can omit short connecting words, but the remaining
        # words and the segment position must agree.
        words = words_without_articles(filename_title)
        if len(words) >= 2 and words == words_without_articles(selected_title):
            continue
        if left != right and (min(len(left), len(right)) < 12 or SequenceMatcher(None, left, right).ratio() < 0.94):
            return None
    return selected


def _unique_episode_title_match(episodes, title):
    key = tvmaze_helper.title_key(title)
    matches = [item for item in episodes
               if type(item.get("number")) is int and item.get("name")
               and key and tvmaze_helper.title_key(item["name"]) == key]
    return matches[0] if len(matches) == 1 else None


def _tvshow_nfo_query(folder, folder_title):
    try:
        with open(os.path.join(folder, "tvshow.nfo"), encoding="utf-8") as file:
            metadata = NFOAgent.parse_nfo_string(file.read()) or {}
    except (OSError, UnicodeError):
        return None
    if metadata.get("type") != "tvshow":
        return None
    id_query = tvmaze_helper.show_id_query(metadata)
    if id_query:
        return id_query
    year = str(metadata.get("year") or "").strip()
    if not re.fullmatch(r"\d{4}", year):
        return None
    title = (metadata.get("title") or "").strip() or folder_title
    return f"{re.sub(r' [(][0-9]{4}[)]$', '', title)} ({year})"


def _tvmaze_episode_name(source, stem, episode):
    folder = os.path.dirname(source)
    season_folder = re.fullmatch(r"season(?:[ ._-]*(\d+))?", os.path.basename(folder), re.I)
    show_folder = os.path.dirname(folder) if season_folder else folder
    folder_title = os.path.basename(show_folder)
    try:
        queries = [folder_title] if re.search(r"\(\d{4}\)$", folder_title) else []
        nfo_query = _tvshow_nfo_query(show_folder, folder_title)
        queries.append(nfo_query)
        filename_query = None
        if episode:
            season, numbers, code = _parse_episode_code(episode.group(1))
            prefix = stem[:episode.start()].strip(" ._-").rstrip("[(").rstrip()
            remix_prefix = re.sub(r"\s*\(\d{4}\)\s*$", "", prefix)
            is_remix = bool(re.search(r"(?:^|[ ._-])remix$", remix_prefix, re.I))
            filename_query = re.sub(r"[ ._-]+remix(?=\s*\(\d{4}\)$|$)", "", prefix, flags=re.I).replace(".", " ")
            if re.search(r"\(\d{4}\)$", filename_query):
                queries.append(filename_query)
        queries.append(folder_title)
        if not season_folder:
            queries.append(filename_query)
        if nfo_query and nfo_query.startswith("tvmaze:"):
            queries = [nfo_query]

        for query in dict.fromkeys(filter(None, queries)):
            matches = tvmaze_helper.search_shows(query)
            if len(matches) > 1:
                options = ", ".join(f"{item['name']} ({item.get('premiered') or 'unknown date'}, ID {item['id']})" for item in matches)
                raise HTTPException(status_code=409, detail=f"Multiple TVmaze shows match {query}: {options}. Set the TVmaze uniqueid in tvshow.nfo.")
            if matches:
                show = matches[0]
                break
        else:
            raise HTTPException(status_code=404, detail=f"No matching TVmaze show for {folder_title}.")

        year = (show.get("premiered") or "")[:4]
        if not re.fullmatch(r"\d{4}", year):
            raise HTTPException(status_code=404, detail=f"TVmaze has no premiere year for {show['name']}.")

        config = StationManager().server_conf
        if episode:
            filename_titles = _filename_episode_titles(stem, episode)
            if is_remix and not re.search(r"\bremix$", show["name"], re.I):
                # A recut can reuse an aired episode code for a different title.
                if not filename_titles:
                    raise HTTPException(status_code=404, detail="This remix filename needs an episode title after its episode code.")
                return f"{show['name']} Remix", year, code, " + ".join(filename_titles)
            configured_orders = config.get("episode_orders", {})
            if (len(filename_titles) == len(numbers) and isinstance(configured_orders, dict)
                    and str(show["id"]) not in configured_orders):
                episode_list = tvmaze_helper.season_episodes(show, season, config)
                segments = _match_broadcast_segments(episode_list, numbers, filename_titles)
                if segments:
                    return show["name"], year, code, _combined_episode_title(segments)
                if len(numbers) == 1:
                    title_match = _unique_episode_title_match(episode_list, filename_titles[0])
                    if title_match:
                        return show["name"], year, code, title_match["name"]
            titles = []
            for number in numbers:
                result = tvmaze_helper.get_episode(show, season, number, config)
                if not result or not result.get("name"):
                    raise HTTPException(status_code=404, detail=f"No episode for {folder_title} S{season:02d}E{number:02d} in the selected order. Check episode_orders in main_config.json.")
                titles.append(result["name"])
            return show["name"], year, code, _combined_episode_title(titles)

        season = int(season_folder[1])
        title = re.sub(r"\s+\(\d{4}\)$", "", stem.strip(" ._-"))
        item = _unique_episode_title_match(tvmaze_helper.season_episodes(show, season, config), title)
        if item:
            return show["name"], year, f"S{season:02d}E{item['number']:02d}", item["name"]
        raise HTTPException(status_code=404, detail=f"No unique episode title match in {folder_title} season {season} in the selected order.")
    except tvmaze_helper.EpisodeOrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=tvmaze_helper.provider_error_detail(exc)) from exc


def _safe_media_title(title):
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', ' ', title)
    return _safe_name(" ".join(title.split()).rstrip("."))


@router.post("/tmdb/normalize/preview")
def preview_tmdb_name(request: CheckTMDBRequest):
    source, extension = _normalization_source(request)
    stem = os.path.basename(source).removesuffix(extension)
    if not extension and re.fullmatch(r"(?:season|series)[ ._-]*\d+|specials", stem, re.I):
        raise HTTPException(status_code=400, detail="Select the show folder instead of a season folder.")

    episode = re.search(
        r"(?<![a-z0-9])(S\d{1,3}E\d{1,3}(?:E\d{1,3}|-E?\d{1,3})*(?!\d)|\d{1,3}x\d{1,3}(?:x\d{1,3})*(?![a-z0-9]))",
        stem, re.I,
    ) if extension else None
    season_directory = os.path.dirname(source)
    in_season = extension and re.fullmatch(r"season[ ._-]*(\d+)", os.path.basename(season_directory), re.I)
    if not episode and in_season:
        bracketed = re.search(r"\[(\d{1,3}\.\d{2,3})\]", stem)
        if bracketed:
            season, number = map(int, bracketed[1].split("."))
            if season == int(in_season[1]) and number > 0:
                episode = bracketed
    if not episode and in_season:
        # Compact codes such as Show901 are only meaningful in a matching show and season folder.
        show_folder = os.path.basename(os.path.dirname(season_directory))
        show_title = re.sub(r"\s*\(\d{4}\)$", "", show_folder)
        for candidate in re.finditer(r"(?<!\d)(\d{3,4})(?=$|[ ._-])", stem):
            compact = candidate[1]
            if (int(compact[:-2]) == int(in_season[1]) and int(compact[-2:]) > 0
                    and tvmaze_helper.title_key(stem[:candidate.start()]) == tvmaze_helper.title_key(show_title)):
                episode = candidate
                break
    if episode or in_season:
        series, year, code, title = _tvmaze_episode_name(source, stem, episode)
        name = f"{_safe_media_title(series)} ({year}) - {code} - {_safe_media_title(title)}"
    else:
        helper = get_tmdb_helper()
        if not helper.is_configured():
            raise HTTPException(status_code=400, detail="TMDB is not configured. Add tmdb_api_key to confs/main_config.json.")
        match = helper.search_media(stem, media_type="movie" if extension else None)
        if not match or not match.get("title"):
            raise HTTPException(status_code=404, detail="No matching title found on TMDB.")
        title = _safe_media_title(match["title"])
        year = (match.get("release_date") or "")[:4]
        name = f"{title} ({year})" if year.isdigit() and len(year) == 4 else title
    name += extension
    return {"name": name, "token": _normalization_token(source, name)}


@router.post("/tmdb/normalize")
def normalize_tmdb_name(request: NormalizeTMDBRequest):
    with NORMALIZATION_LOCK:
        return _normalize_tmdb_name(request)


def _normalize_tmdb_name(request):
    source, extension = _normalization_source(request)
    name = _mounted_rename_name(request.name, extension)
    if not hmac.compare_digest(request.token.encode(), _normalization_token(source, name).encode()):
        raise HTTPException(status_code=409, detail="The preview is stale. Preview this item again.")
    return _rename_mounted_item(source, name)


@router.post("/source/rename")
def rename_source(request: RenameSourceRequest):
    with NORMALIZATION_LOCK:
        source, extension = _mounted_rename_source(request, MEDIA_EXTENSIONS | METADATA_EXTENSIONS | {".json"})
        name = _mounted_rename_name(request.new_name, extension)
        return _rename_mounted_item(source, name)


def _mounted_rename_name(new_name, extension):
    name = _safe_name(new_name)
    if re.search(r'[<>:"|?*\x00-\x1f]', name) or name.endswith(".") or not name.endswith(extension):
        raise HTTPException(status_code=400, detail="Invalid name or changed file extension.")
    return name


def _rename_mounted_item(source, name):
    destination = os.path.join(os.path.dirname(source), name)
    if destination == source:
        return {"name": name, "links_updated": 0}

    try:
        links_updated = _rename_with_catalog_links(source, destination)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="An item with the new name already exists.") from exc
    except OSError as exc:
        location = f" ({exc.filename})" if exc.filename else ""
        raise HTTPException(status_code=409, detail=f"Could not rename the item{location}: {exc.strerror or exc}.") from exc
    return {"name": name, "links_updated": links_updated}


def _rename_without_overwrite(source, destination):
    # Linux renameat2 with RENAME_NOREPLACE protects against a concurrent destination creation.
    rename = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if rename is not None:
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:
            return
        error = ctypes.get_errno()
        if error not in {errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP}:
            raise OSError(error, os.strerror(error), destination)

    # Some mounts reject RENAME_NOREPLACE. Reserve the destination exclusively and
    # replace only the empty entry we created, using the filesystem's standard rename.
    is_directory = os.path.isdir(source)
    if is_directory:
        os.mkdir(destination, mode=0o700)
        reservation = os.lstat(destination)
    else:
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            reservation = os.fstat(fd)
        finally:
            os.close(fd)

    try:
        if not os.path.samestat(os.lstat(destination), reservation):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), destination)
        os.replace(source, destination)
    except OSError:
        try:
            if os.path.samestat(os.lstat(destination), reservation):
                if is_directory:
                    os.rmdir(destination)
                else:
                    os.unlink(destination)
        except FileNotFoundError:
            pass
        raise


def _rename_with_catalog_links(source, destination):
    if _inside(CATALOG_ROOT, source):
        raise OSError("Cannot rename a directory that contains the catalog")
    with ExitStack() as staging:
        updates = []
        for link in _export_catalog_links_data(strict=True)["links"]:
            path = _catalog_entry(link["path"])
            old_target = os.readlink(path)
            parent = os.path.dirname(path)
            target = os.path.abspath(os.path.join(parent, old_target))
            if target != source and not target.startswith(source + os.sep):
                target = os.path.realpath(path)
                if not _inside(target, source):
                    continue
            suffix = os.path.relpath(target, source)
            new_target = destination if suffix == "." else os.path.join(destination, suffix)
            if not os.path.isabs(old_target):
                new_target = os.path.relpath(new_target, parent)
            temporary = staging.enter_context(TemporaryDirectory(prefix=".fs42-relink-", dir=parent))
            replacement = os.path.join(temporary, "new")
            backup = os.path.join(temporary, "old")
            os.symlink(new_target, replacement)
            os.symlink(old_target, backup)
            updates.append((path, old_target, new_target, replacement, backup))

        _rename_without_overwrite(source, destination)
        applied = []
        try:
            for path, old_target, new_target, replacement, backup in updates:
                if os.readlink(path) != old_target:
                    raise OSError(f"Catalog link changed during rename: {path}")
                os.replace(replacement, path)
                applied.append((path, new_target, backup))
        except OSError as exc:
            try:
                _rename_without_overwrite(destination, source)
            except OSError as rollback_error:
                raise HTTPException(status_code=500, detail=f"The item was renamed to {destination}, but a catalog link update failed and the rename could not be rolled back: {rollback_error}") from exc
            failed = []
            for path, new_target, backup in reversed(applied):
                try:
                    if os.readlink(path) == new_target:
                        os.replace(backup, path)
                except OSError:
                    failed.append(os.path.relpath(path, CATALOG_ROOT))
            if failed:
                raise HTTPException(status_code=500, detail=f"The item name was restored, but these catalog links could not be restored: {', '.join(failed)}.") from exc
            raise
        return len(updates)


@router.get("/catalog")
async def browse_catalog(path: str = ""):
    directory = _catalog_directory(path)
    relative_path = _relative_path(path).replace(os.sep, "/")
    entries = []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                try:
                    if entry.is_symlink():
                        entries.append({
                            "name": entry.name,
                            "type": "link",
                            "target": os.readlink(entry.path),
                            "is_directory": os.path.isdir(entry.path),
                        })
                    elif entry.is_dir(follow_symlinks=False):
                        entries.append({"name": entry.name, "type": "directory"})
                    else:
                        entries.append({"name": entry.name, "type": "file"})
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while reading catalog/.")
    entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].lower()))
    return {"path": relative_path, "entries": entries}


def _export_catalog_links_data(strict=False):
    os.makedirs(CATALOG_ROOT, exist_ok=True)
    links = []

    def raise_walk_error(error):
        raise error

    for current, directories, files in os.walk(
        CATALOG_ROOT, followlinks=False, onerror=raise_walk_error if strict else None,
    ):
        relative_directory = os.path.relpath(current, CATALOG_ROOT)
        relative_directory = "" if relative_directory == "." else relative_directory.replace(os.sep, "/")
        for name in list(directories):
            path = os.path.join(current, name)
            if os.path.islink(path):
                links.append({
                    "path": "/".join(part for part in (relative_directory, name) if part),
                    "target": os.path.realpath(path),
                })
                directories.remove(name)
        for name in files:
            path = os.path.join(current, name)
            if os.path.islink(path):
                links.append({
                    "path": "/".join(part for part in (relative_directory, name) if part),
                    "target": os.path.realpath(path),
                })
    links.sort(key=lambda link: link["path"].lower())
    return {"version": 1, "links": links}


@router.get("/export")
async def export_catalog_links():
    return _export_catalog_links_data()


@router.post("/export-to-drive")
async def export_catalog_links_to_drive(request: DriveCatalogFileRequest):
    mount_root, directory, _ = _source_path(request.mount, request.path)
    filename = _safe_name(request.filename)
    if not filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Export filename must end in .json.")
    destination = os.path.abspath(os.path.join(directory, filename))
    if not _inside(destination, mount_root):
        raise HTTPException(status_code=400, detail="Export destination must stay on the selected drive.")
    data = _export_catalog_links_data()
    try:
        with open(destination, "x", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2)
            fp.write("\n")
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"A file named {filename} already exists.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while writing to the mounted drive.")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not export links to the mounted drive: {exc}")
    return {"success": True, "filename": filename, "count": len(data["links"])}


def _mounted_target(target):
    canonical = os.path.realpath(target)
    for mount in _mounts():
        mount_root = mount["path"]
        if canonical == mount_root:
            continue
        if _inside(canonical, mount_root):
            relative = os.path.relpath(canonical, mount_root)
            root, source, relative_source = _source_path(mount_root, relative)
            if relative_source and (os.path.isdir(source) or (os.path.isfile(source) and os.path.splitext(source)[1].lower() in MEDIA_EXTENSIONS)):
                return source
    raise HTTPException(status_code=400, detail=f"Link target is not a directory or supported media file on a mounted drive: {target}")


def _catalog_destination(relative_path):
    relative = _relative_path(relative_path)
    if not relative:
        raise HTTPException(status_code=400, detail="A link path is required.")
    parts = relative.split(os.sep)
    name = _safe_name(parts[-1])
    parent_relative = os.path.join(*parts[:-1]) if len(parts) > 1 else ""
    destination = os.path.abspath(os.path.join(CATALOG_ROOT, relative))
    if not _inside(os.path.dirname(destination), CATALOG_ROOT):
        raise HTTPException(status_code=400, detail="Link destination must stay inside catalog/.")
    return parent_relative, name, destination


def _validate_import_parent(relative_path):
    current = CATALOG_ROOT
    for part in (relative_path.split(os.sep) if relative_path else []):
        current = os.path.join(current, part)
        if os.path.lexists(current):
            if os.path.islink(current) or not os.path.isdir(current):
                raise HTTPException(status_code=400, detail="Import destination cannot pass through a link or non-directory.")
        else:
            break


def _import_catalog_links_data(request: ImportCatalogLinksRequest):
    if request.version != 1:
        raise HTTPException(status_code=400, detail="Unsupported catalog links export version.")
    if len(request.links) > 10000:
        raise HTTPException(status_code=413, detail="The import contains too many links (limit 10,000).")

    plans = []
    destinations = set()
    for link in request.links:
        parent_relative, name, destination = _catalog_destination(link.path)
        key = os.path.normcase(destination)
        if key in destinations:
            raise HTTPException(status_code=400, detail=f"Duplicate destination in import: {link.path}")
        destinations.add(key)
        source = _mounted_target(link.target)
        plans.append((parent_relative, name, destination, source, link.path))

    for parent_relative, _, destination, _, link_path in plans:
        _validate_import_parent(parent_relative)
        if os.path.lexists(destination):
            raise HTTPException(status_code=409, detail=f"Catalog entry already exists: {link_path}")

    for parent_relative, _, _, _, link_path in plans:
        parent_parts = parent_relative.split(os.sep) if parent_relative else []
        for index in range(1, len(parent_parts) + 1):
            parent_destination = os.path.normcase(os.path.join(CATALOG_ROOT, *parent_parts[:index]))
            if parent_destination in destinations:
                raise HTTPException(status_code=400, detail=f"A link destination is also used as a parent directory: {link_path}")

    for parent_relative, _, destination, source, _ in plans:
        parent_parts = parent_relative.split(os.sep) if parent_relative else []
        current = CATALOG_ROOT
        for part in parent_parts:
            current = os.path.join(current, part)
            if os.path.lexists(current):
                if os.path.islink(current) or not os.path.isdir(current):
                    raise HTTPException(status_code=400, detail="Import destination cannot pass through a link or non-directory.")
            else:
                os.mkdir(current)
        if not _inside(os.path.dirname(destination), CATALOG_ROOT):
            raise HTTPException(status_code=400, detail="Link destination must stay inside catalog/.")
        os.symlink(source, destination)
    return {"success": True, "created": len(plans)}


@router.post("/import")
async def import_catalog_links(request: ImportCatalogLinksRequest):
    return _import_catalog_links_data(request)


@router.post("/import-from-drive")
async def import_catalog_links_from_drive(request: DriveCatalogFileRequest):
    mount_root, directory, _ = _source_path(request.mount, request.path)
    filename = _safe_name(request.filename)
    if not filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Choose a .json catalog links file.")
    source = os.path.realpath(os.path.join(directory, filename))
    if not _inside(source, mount_root) or not os.path.isfile(source):
        raise HTTPException(status_code=404, detail="Catalog links JSON file not found on the selected drive.")
    if os.path.getsize(source) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Catalog links JSON file is larger than 10 MB.")
    try:
        with open(source, encoding="utf-8") as fp:
            payload = json.load(fp)
        import_request = ImportCatalogLinksRequest(**payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid catalog links JSON file: {exc}")
    return _import_catalog_links_data(import_request)


@router.post("/directory")
async def create_catalog_directory(request: CreateDirectoryRequest):
    parent = _catalog_directory(request.path)
    name = _safe_name(request.name)
    destination = os.path.join(parent, name)
    try:
        os.mkdir(destination)
    except FileExistsError:
        raise HTTPException(status_code=409, detail="An entry with that name already exists.")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while creating the directory.")
    return {"success": True, "name": name}


@router.post("/link")
async def create_catalog_link(request: CreateLinkRequest):
    mount_root, source, relative_source = _source_path(request.mount, request.source_path)
    if not relative_source:
        raise HTTPException(status_code=400, detail="The mounted drive root cannot be linked into catalog/.")
    if not _inside(source, mount_root):
        raise HTTPException(status_code=400, detail="Source path must stay on the selected drive.")
    if os.path.isdir(source):
        pass
    elif os.path.isfile(source) and os.path.splitext(source)[1].lower() in MEDIA_EXTENSIONS:
        pass
    elif os.path.isfile(source):
        raise HTTPException(status_code=400, detail="This file type is not supported as catalog media.")
    else:
        raise HTTPException(status_code=400, detail="Select a mounted-drive directory or supported media file.")
    destination_directory = _catalog_directory(request.catalog_path)
    link_name = _safe_name(request.link_name or os.path.basename(source))
    destination = os.path.join(destination_directory, link_name)
    if os.path.lexists(destination):
        raise HTTPException(status_code=409, detail="An entry with that name already exists in this catalog directory.")
    try:
        os.symlink(source, destination)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while creating the media link.")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not create the media link: {exc}")
    return {"success": True, "name": link_name, "target": source}


@router.post("/rename")
async def rename_catalog_entry(request: RenameEntryRequest):
    source = _catalog_entry(request.path)
    parent = os.path.dirname(source)
    name = _safe_name(request.new_name)
    destination = os.path.join(parent, name)
    try:
        if os.path.lexists(destination):
            raise HTTPException(status_code=409, detail="An entry with that name already exists.")
        if not os.path.islink(source) and not os.path.isdir(source):
            raise HTTPException(status_code=400, detail="Only directories and media links can be renamed.")
        os.rename(source, destination)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while renaming the catalog entry.")
    return {"success": True, "name": name}


@router.post("/delete")
async def delete_catalog_entry(request: DeleteEntryRequest):
    entry = _catalog_entry(request.path)
    try:
        if os.path.islink(entry):
            os.unlink(entry)
        elif os.path.isdir(entry):
            os.rmdir(entry)
        else:
            raise HTTPException(status_code=400, detail="Only directories and media links can be removed.")
    except OSError as exc:
        if exc.errno in {errno.ENOTEMPTY, errno.EEXIST}:
            raise HTTPException(status_code=409, detail="Directory is not empty.")
        if isinstance(exc, PermissionError):
            raise HTTPException(status_code=403, detail="Permission denied while removing the catalog entry.")
        raise HTTPException(status_code=500, detail=f"Could not remove catalog entry: {exc}")
    return {"success": True}
