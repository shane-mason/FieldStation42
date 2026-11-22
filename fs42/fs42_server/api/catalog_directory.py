import errno
import json
import os
import re
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fs42.fs42_server.api.media import AUDIO_EXTENSIONS, PROJECT_ROOT, VIDEO_EXTENSIONS

router = APIRouter(prefix="/catalog-directory", tags=["catalog-directory"])

CATALOG_ROOT = os.path.realpath(os.path.join(PROJECT_ROOT, "catalog"))
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
PSEUDO_FILESYSTEMS = {
    "autofs", "bpf", "cgroup", "cgroup2", "configfs", "debugfs", "devpts",
    "devtmpfs", "efivarfs", "fusectl", "mqueue", "overlay", "proc", "pstore",
    "securityfs", "sysfs", "tracefs", "tmpfs",
}
NETWORK_FILESYSTEMS = {"9p", "cifs", "fuse.sshfs", "nfs", "nfs4", "smb3"}
EXCLUDED_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/boot")


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
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while reading this drive.")
    entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].lower()))
    return {"path": relative_path.replace(os.sep, "/"), "entries": entries}


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


def _export_catalog_links_data():
    os.makedirs(CATALOG_ROOT, exist_ok=True)
    links = []
    for current, directories, files in os.walk(CATALOG_ROOT, followlinks=False):
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
