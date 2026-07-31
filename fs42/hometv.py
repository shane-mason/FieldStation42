"""Headless schedule resolution and browser HLS session management."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fs42.catalog_api import CatalogAPI
from fs42.liquid_api import LiquidAPI
from fs42.station_manager import StationManager

LOG = logging.getLogger("HomeTV")
ASSET_RE = re.compile(r"^(?:master\.m3u8|stream\d+\.ts)$")


class WatchError(Exception):
    """A watch request cannot be fulfilled."""


class ChannelNotFound(WatchError):
    pass


class ProgramNotFound(WatchError):
    pass


class UnsafeMediaPath(WatchError):
    pass


@dataclass(frozen=True)
class Airing:
    channel_number: str
    channel_name: str
    program_title: str
    item_title: str
    start: dt.datetime
    end: dt.datetime
    item_start: dt.datetime
    item_end: dt.datetime
    media_path: str
    offset: float
    duration: float
    remaining: float

    def public_dict(self, now: dt.datetime) -> dict:
        elapsed = max(0.0, min((now - self.start).total_seconds(), self.duration))
        return {
            "channel_number": self.channel_number,
            "channel_name": self.channel_name,
            "program_title": self.program_title,
            "item_title": self.item_title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "item_end": self.item_end.isoformat(),
            "duration": self.duration,
            "elapsed": elapsed,
            "progress": elapsed / self.duration if self.duration > 0 else 0,
            "playback_offset": self.offset,
            "server_time": now.isoformat(),
        }


def _local_now() -> dt.datetime:
    return dt.datetime.now()


class ScheduleResolver:
    """Resolve an opaque channel selection to its current scheduled media."""

    def __init__(self, manager: StationManager | None = None):
        self.manager = manager or StationManager()

    def channels(self) -> list[dict]:
        channels = []
        for station in self.manager.stations:
            if station.get("hidden") or not station.get("_has_schedule", False):
                continue
            channels.append(
                {
                    "channel_number": str(station["channel_number"]),
                    "channel_name": station["network_name"],
                }
            )
        return channels

    def station(self, channel: str):
        value = str(channel)
        for station in self.manager.stations:
            if (
                str(station.get("channel_number")) == value
                or station.get("network_name") == value
            ):
                if station.get("_has_schedule", False) and not station.get("hidden"):
                    return station
                break
        raise ChannelNotFound(f"Unknown scheduled channel: {channel}")

    def now(self, channel: str, when: dt.datetime | None = None) -> Airing:
        when = when or _local_now()
        station = self.station(channel)
        # Query a one-microsecond interval so SQLite selects only a covering row.
        blocks = LiquidAPI.get_blocks(
            station, when, when + dt.timedelta(microseconds=1)
        )
        block = next(
            (
                item
                for item in (blocks or [])
                if item.start_time <= when < item.end_time
            ),
            None,
        )
        if block is None:
            raise ProgramNotFound(
                f"No programming is scheduled now on {station['network_name']}"
            )

        cursor = block.start_time
        selected = None
        for item in block.plan:
            item_end = cursor + dt.timedelta(seconds=max(0, item.duration))
            if cursor <= when < item_end:
                selected = (item, cursor, item_end)
                break
            cursor = item_end
        if selected is None:
            raise ProgramNotFound("The current schedule block has no playable item")

        item, item_start, item_end = selected
        if item.is_stream:
            raise ProgramNotFound("Live URL schedule items are not supported by the MVP")
        media_path = self._approved_media_path(station, item.path)
        offset = max(0.0, float(item.skip) + (when - item_start).total_seconds())
        item_title = Path(item.path).stem
        return Airing(
            channel_number=str(station["channel_number"]),
            channel_name=station["network_name"],
            program_title=block.title,
            item_title=item_title,
            start=block.start_time,
            end=block.end_time,
            item_start=item_start,
            item_end=item_end,
            media_path=media_path,
            offset=offset,
            duration=(block.end_time - block.start_time).total_seconds(),
            remaining=(item_end - when).total_seconds(),
        )

    @staticmethod
    def _approved_media_path(station: dict, scheduled_path: str) -> str:
        requested = os.path.realpath(scheduled_path)
        for entry in CatalogAPI.get_entries(station) or []:
            candidates = [entry.path, getattr(entry, "realpath", None)]
            if any(path and os.path.realpath(path) == requested for path in candidates):
                if not os.path.isfile(requested):
                    raise ProgramNotFound("The scheduled media file is unavailable")
                return requested
        raise UnsafeMediaPath("Scheduled media is not present in the channel catalog")


@dataclass
class StreamSession:
    session_id: str
    channel: str
    profile: str
    directory: Path
    process: subprocess.Popen
    created_at: float
    last_access: float


class HLSSessionManager:
    PROFILES = {"auto", "copy"}

    def __init__(
        self,
        resolver: ScheduleResolver | None = None,
        root: str | Path | None = None,
        idle_seconds: int | None = None,
        max_sessions: int | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ):
        conf = StationManager().server_conf
        self.resolver = resolver or ScheduleResolver()
        self.root = Path(
            root
            or os.environ.get("FS42_HLS_DIR")
            or conf.get("hls_dir", "runtime/hls")
        ).resolve()
        self.idle_seconds = int(
            idle_seconds
            or os.environ.get("FS42_HLS_IDLE_SECONDS")
            or conf.get("hls_idle_seconds", 90)
        )
        self.max_sessions = int(
            max_sessions
            or os.environ.get("FS42_HLS_MAX_SESSIONS")
            or conf.get("hls_max_sessions", 8)
        )
        self.process_factory = process_factory
        self.sessions: dict[str, StreamSession] = {}
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        # A single production worker owns this cache. Remove only UUID-shaped
        # directories left behind by a previous unclean container shutdown.
        for child in self.root.iterdir():
            try:
                uuid.UUID(child.name)
            except (ValueError, AttributeError):
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    def create(self, channel: str, profile: str = "auto") -> tuple[StreamSession, Airing]:
        if profile not in self.PROFILES:
            raise ValueError(f"Unknown client profile: {profile}")
        with self.lock:
            self.cleanup()
            if len(self.sessions) >= self.max_sessions:
                raise WatchError("The server has reached its stream session limit")
            airing = self.resolver.now(channel)
            session_id = str(uuid.uuid4())
            directory = self.root / session_id
            directory.mkdir(mode=0o700)
            subtitle = (
                self._english_subtitle(airing.media_path)
                if profile == "auto"
                else None
            )
            command = self._ffmpeg_command(airing, profile, directory, subtitle)
            LOG.info(
                "Starting HLS session %s for channel %s at %.3fs (%s)",
                session_id,
                airing.channel_number,
                airing.offset,
                profile,
            )
            try:
                process = self.process_factory(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=None,
                    start_new_session=True,
                )
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            timestamp = time.monotonic()
            session = StreamSession(
                session_id, airing.channel_number, profile, directory, process,
                timestamp, timestamp
            )
            self.sessions[session_id] = session
            return session, airing

    @staticmethod
    def _english_subtitle(media_path: str) -> tuple[str, int] | None:
        """Select an English subtitle only for explicitly non-English audio."""
        try:
            result = subprocess.run(
                [
                    os.environ.get("FS42_FFPROBE", "ffprobe"),
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name:stream_tags=language",
                    "-of",
                    "json",
                    media_path,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            streams = __import__("json").loads(result.stdout).get("streams", [])
        except Exception as exc:
            LOG.warning("Could not inspect subtitle languages for %s: %s", media_path, exc)
            return None

        audio = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )
        audio_language = (
            (audio or {}).get("tags", {}).get("language", "und").casefold()
        )
        if audio_language in {"eng", "en", "und", ""}:
            return None

        subtitles = [
            stream for stream in streams if stream.get("codec_type") == "subtitle"
        ]
        for index, stream in enumerate(subtitles):
            language = stream.get("tags", {}).get("language", "").casefold()
            if language in {"eng", "en"}:
                return stream.get("codec_name", ""), index
        return None

    @staticmethod
    def _ffmpeg_command(
        airing: Airing,
        profile: str,
        directory: Path,
        subtitle: tuple[str, int] | None = None,
    ) -> list[str]:
        command = [
            os.environ.get("FS42_FFMPEG", "ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-ss",
            f"{airing.offset:.3f}",
            "-re",
            "-i",
            airing.media_path,
            "-t",
            f"{max(0.1, airing.remaining):.3f}",
        ]
        if profile == "copy":
            command += ["-c", "copy"]
        else:
            video_map = "0:v:0"
            video_filter = []
            if subtitle:
                codec, subtitle_index = subtitle
                if codec in {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}:
                    command += [
                        "-filter_complex",
                        f"[0:v:0][0:s:{subtitle_index}]overlay[v]",
                    ]
                    video_map = "[v]"
                else:
                    escaped_path = (
                        airing.media_path.replace("\\", "\\\\")
                        .replace(":", "\\:")
                        .replace("'", "\\'")
                    )
                    video_filter = [
                        "-vf",
                        f"subtitles='{escaped_path}':si={subtitle_index}",
                    ]
            command += [
                "-map",
                video_map,
                "-map",
                "0:a:0?",
                *video_filter,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-force_key_frames",
                "expr:gte(t,n_forced*2)",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
            ]
        command += [
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "12",
            "-hls_flags",
            "delete_segments+independent_segments+omit_endlist",
            "-hls_segment_filename",
            str(directory / "stream%05d.ts"),
            str(directory / "master.m3u8"),
        ]
        return command

    def get(self, session_id: str) -> StreamSession:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            session.last_access = time.monotonic()
            return session

    def asset(self, session_id: str, asset: str) -> Path:
        if not ASSET_RE.fullmatch(asset):
            raise ValueError("Invalid HLS asset")
        session = self.get(session_id)
        target = (session.directory / asset).resolve()
        if target.parent != session.directory.resolve():
            raise ValueError("Invalid HLS asset")
        return target

    def delete(self, session_id: str) -> bool:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            return False
        self._stop(session)
        return True

    def cleanup(self) -> None:
        cutoff = time.monotonic() - self.idle_seconds
        with self.lock:
            expired = [
                key
                for key, session in self.sessions.items()
                if session.last_access < cutoff or session.process.poll() is not None
            ]
        for key in expired:
            self.delete(key)

    def close(self) -> None:
        with self.lock:
            session_ids = list(self.sessions)
        for session_id in session_ids:
            self.delete(session_id)

    @staticmethod
    def _stop(session: StreamSession) -> None:
        if session.process.poll() is None:
            session.process.terminate()
            try:
                session.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                session.process.kill()
                session.process.wait(timeout=2)
        shutil.rmtree(session.directory, ignore_errors=True)
