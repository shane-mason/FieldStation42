import json
import logging
import re
import secrets
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime

from fs42.station_manager import StationManager

station_manager = StationManager()
station_configs = station_manager.stations

LOG = logging.getLogger(__name__)

USER_AGENT = "FS42-StreamAgent/1.0"


def usable(value):
    """Return False for missing or empty values."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def get_path(data, path):
    """Read a dot-separated path from nested dictionaries or lists."""
    if path == "$":
        return data

    current = data

    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None

        if current is None:
            return None

    return current


def get_first_value(data, paths):
    """Try one path or an ordered list of fallback paths."""
    if isinstance(paths, str):
        paths = [paths]

    for path in paths or []:
        value = get_path(data, path)

        if usable(value):
            return value

    return None


def fetch_json(url, timeout=8.0, params=None, headers=None):
    """Fetch and decode a JSON endpoint."""
    from urllib.parse import urlencode

    if params:
        separator = "&" if "?" in url else "?"
        url = url + separator + urlencode(params, doseq=True)

    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    request_headers.update(headers or {})

    request = urllib.request.Request(url, headers=request_headers)

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def select_record(payload, config):
    """Select a record from a response using the configured rules."""
    records_path = config.get("records_key", "$")
    records = get_path(payload, records_path)

    if records is None:
        return None

    if not isinstance(records, list):
        records = [records]

    selection = config.get("select", {})
    mode = selection.get("mode", "first")
    required = selection.get("require_any", [])

    if mode == "last":
        records = reversed(records)

    for record in records:
        if not isinstance(record, (dict, list)):
            continue

        if mode == "first_matching":
            if not any(usable(get_path(record, path)) for path in required):
                continue

        return record

    return None


def extract_fields(record, fields):
    """Map configured response paths to normalized metadata fields."""
    result = {}

    for name, paths in fields.items():
        if name == "follow_up":
            continue

        value = get_first_value(record, paths)

        if value is not None:
            result[name] = value

    return result

def fetch_icy_metadata(stream_url, metadata_config=None):
    """Fetch and normalize ICY metadata using station configuration."""
    metadata_config = metadata_config or {}

    request = urllib.request.Request(
        stream_url,
        headers={
            "Icy-MetaData": "1",
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        interval = int(response.headers.get("icy-metaint", "0"))
        if not interval:
            return {}

        last_title = ""

        # ICY metadata may be empty in the first block.
        max_blocks = metadata_config.get("max_blocks", 30)

        for _ in range(max_blocks):
            audio = response.read(interval)
            if len(audio) != interval:
                break

            length_byte = response.read(1)
            if not length_byte:
                break

            metadata_length = length_byte[0] * 16
            if not metadata_length:
                continue

            raw = response.read(metadata_length)
            if len(raw) != metadata_length:
                break

            metadata_text = raw.rstrip(b"\0").decode(
                "utf-8", errors="replace"
            )

            raw_fields = dict(re.findall(
                r"""([A-Za-z][A-Za-z0-9_]*)='(.*?)';""",
                metadata_text,
            ))

            title = raw_fields.get("StreamTitle", "").strip()
            if title:
                last_title = title

            # Parse configured compound fields into virtual fields,
            # e.g. track.artist and track.song.
            values = dict(raw_fields)

            for name, rule in metadata_config.items():
                if not isinstance(rule, dict):
                    continue

                source = rule.get("source")
                pattern = rule.get("pattern")
                if not source or not pattern:
                    continue

                source_value = raw_fields.get(source, "").strip()
                if not source_value:
                    continue

                match = re.search(pattern, source_value)
                if not match:
                    continue

                for key, value in match.groupdict().items():
                    if value and value.strip():
                        values[f"{name}.{key}"] = value.strip()

            # Resolve normalized fields in configured priority order.
            result = {}

            for output_field, sources in metadata_config.get(
                "fields", {}
            ).items():
                if isinstance(sources, str):
                    sources = [sources]

                for source in sources:
                    value = values.get(source, "")
                    if value and str(value).strip():
                        result[output_field] = str(value).strip()
                        break

            # Preserve the raw title as a fallback for diagnostics or
            # stations whose format hasn't been configured yet.
            if title:
                result["stream_title"] = title

            # Prefer a block that produced normalized metadata.
            if any(
                key != "stream_title" and value
                for key, value in result.items()
            ):
                return result

        # No configured fields matched, but retain the last title seen.
        return {"stream_title": last_title} if last_title else {}

def fetch_metadata(stream_config):
    """Fetch normalized metadata for one configured stream."""
    config = stream_config.get("metadata_config", {})
    url = stream_config.get("metadata_url")

    if not url:
        return empty_metadata(config.get("fields", {}))

    timeout = float(config.get("timeout", 8.0))

    payload = fetch_json(
        url,
        timeout=timeout,
        params=config.get("params"),
        headers=config.get("headers"),
    )

    record = select_record(payload, config)

    if record is None:
        return empty_metadata(config.get("fields", {}))

    fields = config.get("fields", {})
    result = extract_fields(record, fields)

    follow_up = fields.get("follow_up")

    if isinstance(follow_up, dict):
        follow_url = get_first_value(record, follow_up.get("url_path"))

        if usable(follow_url):
            # Resolve relative URLs against the primary endpoint.
            follow_url = urljoin(url, str(follow_url))

            # Only follow URLs on the primary endpoint's origin.
            primary = urlparse(url)
            secondary = urlparse(follow_url)

            if (
                secondary.scheme == "https"
                and secondary.hostname == primary.hostname
                and secondary.port == primary.port
            ):
                try:
                    extra_payload = fetch_json(
                        follow_url,
                        timeout=timeout,
                        headers=config.get("headers"),
                    )

                    extra_fields = {
                        key: value
                        for key, value in follow_up.items()
                        if key != "url_path"
                    }

                    result.update({
                        key: value
                        for key, value in extract_fields(extra_payload, extra_fields).items()
                        if not usable(result.get(key)) and usable(value)
                    })
                except Exception as exc:
                    LOG.warning("Metadata follow-up request failed: %s", exc)

            else:
                LOG.warning("Rejected follow-up URL outside the primary origin")

    return {
        key: ", ".join(str(item) for item in value)
        if isinstance(value, list)
        else value
        for key, value in result.items()
    }


def download_artwork(url, output_dir):
    """Download artwork to a randomly named image file."""
    if not usable(url):
        return None

    parsed = urlparse(str(url))

    if parsed.scheme != "https" or not parsed.hostname:
        LOG.warning("Rejected invalid artwork URL")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        str(url),
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            content_type = response.headers.get_content_type()

            extensions = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
            }

            extension = extensions.get(content_type)

            if not extension:
                LOG.warning("Unsupported artwork content type: %s", content_type)
                return None

            data = response.read(10 * 1024 * 1024 + 1)

            if not data or len(data) > 10 * 1024 * 1024:
                LOG.warning("Artwork is empty or exceeds the size limit")
                return None

        filename = f"radio_art_{secrets.token_hex(8)}{extension}"
        destination = output_dir / filename
        destination.write_bytes(data)

        return str(destination)

    except Exception as exc:
        LOG.warning("Artwork download failed: %s", exc)
        return None
        
def find_active_stream(play_status, station_configs):
    if play_status.get("status") != "playing":
        return None

    if play_status.get("content_type") != "stream":
        return None

    file_path = play_status.get("file_path")
    network_name = play_status.get("network_name", "")

    if not file_path or not network_name:
        return None

    for station in station_configs:
        if station.get("network_name", "").casefold() != network_name.casefold():
            continue

        for stream in station.get("streams", []):
            if stream.get("url") == file_path:
                return station, stream

    return None

def empty_metadata(fields):
    return {
        key: " "
        for key in fields
        if key != "follow_up"
    }    

class StreamAgent:
    """Poll the active stream and publish its metadata for the OSD."""

    def __init__(
        self,
        status_path="runtime/play_status.socket",
        output_path="runtime/stream_metadata.socket",
        artwork_dir="runtime",
        station_manager=None,
        check_interval=1.0,
    ):
        self.status_path = Path(status_path)
        self.output_path = Path(output_path)
        self.artwork_dir = Path(artwork_dir)
        self._cleanup_stale_artwork()
        self.station_manager = station_manager or StationManager()
        self.check_interval = check_interval

        self._stop_event = threading.Event()
        self._thread = None

        self._active_key = None
        self._last_poll = 0.0
        self._last_metadata = {}
        self._metadata_keys = {
            "network_name",
            "channel_number",
            "stream_url",
            "show",
            "host",
            "artwork",
            "artist",
            "song",
            "album",
            "tagline",
        }
        self._artwork_path = None
        self._artwork_url = None

    def start(self):
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._publish(self._blank_metadata())

        self._thread = threading.Thread(
            target=self._run,
            name="StreamAgent",
            daemon=True,
        )
        self._thread.start()
        LOG.info("StreamAgent started")

    def stop(self):
        """Stop the background polling thread."""
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        LOG.info("StreamAgent stopped")

    def _blank_metadata(self, stream=None):
        """Return blank values for all known metadata fields."""
        keys = set(self._metadata_keys)

        if stream is None:
            active_url = self._active_key[1] if self._active_key else None
            stream = next(
                (
                    s
                    for station in self.station_manager.stations
                    for s in station.get("streams", [])
                    if s.get("url") == active_url
                ),
                None,
            )

        if stream:
            fields = stream.get("metadata_config", {}).get("fields", {})
            keys.update(key for key in fields if key != "follow_up")

        return {key: " " for key in keys}
        
    def _read_status(self):
        try:
            with self.status_path.open("r", encoding="utf-8") as status_file:
                return json.load(status_file)
        except (OSError, json.JSONDecodeError) as exc:
            LOG.debug("Unable to read playback status: %s", exc)
            return {}

    def _publish(self, metadata):
        """Replace the published metadata JSON."""
        self._metadata_keys.update(metadata.keys())
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        temporary_path = self.output_path.with_suffix(
            self.output_path.suffix + ".tmp"
        )

        try:
            with temporary_path.open("w", encoding="utf-8") as output_file:
                json.dump(metadata, output_file, ensure_ascii=False)
                output_file.write("\n")

            temporary_path.replace(self.output_path)

        except OSError:
            LOG.exception("Unable to publish stream metadata")
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _remove_artwork(self):
        """Remove the artwork file currently owned by this agent."""
        if self._artwork_path:
            try:
                Path(self._artwork_path).unlink(missing_ok=True)
            except OSError:
                LOG.warning(
                    "Unable to remove old artwork file: %s",
                    self._artwork_path,
                    exc_info=True,
                )

        self._artwork_path = None
        self._artwork_url = None

    def _cleanup_stale_artwork(self):
        """Remove leftover radio artwork files from previous runs."""
        from pathlib import Path

        artwork_dir = Path(self.artwork_dir)

        if not artwork_dir.is_dir():
            return

        for path in artwork_dir.glob("radio_art_*"):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
            except OSError as exc:
                self.logger.warning(
                    "Failed to remove stale artwork %s: %s", path, exc
                )

    def _clear(self):
        """Clear published metadata and remove the current artwork."""
        self._last_metadata = {}
        self._remove_artwork()
        self._publish(self._blank_metadata())

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._update()
            except Exception:
                LOG.exception("StreamAgent update failed")

            self._stop_event.wait(self.check_interval)

    def _update(self):
        status = self._read_status()
        print(f"DEBUG playback status: {self._read_status()}")
        match = find_active_stream(status, self.station_manager.stations)
        print(f"DEBUG match: {match}")
        if match is None:
            self._clear()
            self._active_key = None
            return

        station, stream = match
        active_key = (
            station.get("network_name"),
            stream.get("url"),
        )

        changed = active_key != self._active_key

        if changed:
            self._remove_artwork()
            self._active_key = active_key
            self._last_poll = 0.0
            self._last_metadata = {}

            blank_metadata = self._blank_metadata(stream)
            self._publish(blank_metadata)

        now = time.monotonic()

        interval = float(
            stream.get("metadata_config", {}).get("interval", 15.0)
        )

        if not changed and now - self._last_poll < interval:
            return

        self._last_poll = now
        print(f"DEBUG metadata_type: {stream.get('metadata_type')}")
        try:
            if stream.get("metadata_type") == "icy":
                metadata = fetch_icy_metadata(stream["url"], stream.get("metadata_config", {}),)
            else:
                metadata = fetch_metadata(stream)
            print(f"DEBUG stream_config: {stream}")
            print(f"DEBUG fetched metadata: {metadata}")
        except Exception as exc:
            LOG.warning(
                "Metadata fetch failed for %s: %s",
                station.get("network_name"),
                exc,
            )
            # Retain the last valid metadata after transient failures.
            return

        if not metadata:
            metadata = {}

        for key in self._metadata_keys:
            metadata.setdefault(key, " ")
            
        metadata["network_name"] = station.get("network_name")
        metadata["channel_number"] = station.get("channel_number")
        metadata["stream_url"] = stream.get("url")


        artwork_url = metadata.pop("artwork", None)

        if usable(artwork_url):
            artwork_url = str(artwork_url)

        # Keep the existing file if the artwork URL hasn't changed.
        if artwork_url != self._artwork_url:
            new_artwork_path = None

            if artwork_url:
                new_artwork_path = download_artwork(
                    artwork_url,
                    self.artwork_dir,
                )

            if new_artwork_path:
                # Replacement downloaded successfully: remove the old file.
                self._remove_artwork()
                self._artwork_path = new_artwork_path
                self._artwork_url = artwork_url
            elif not artwork_url:
                # The new metadata explicitly has no artwork.
                self._remove_artwork()
            else:
                # Download failed; retain the previous artwork if available.
                LOG.warning(
                    "Keeping existing artwork after download failure"
                )

        if self._artwork_path:
            metadata["artwork"] = self._artwork_path

        self._last_metadata = metadata
        self._publish(metadata)

