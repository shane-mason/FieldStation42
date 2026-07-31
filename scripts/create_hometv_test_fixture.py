#!/usr/bin/env python3
"""Create isolated two-channel HomeTV state and generated test media."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
from pathlib import Path


def generate_media(path: Path, source: str, frequency: int, duration: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "48",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def station_config(name: str, channel: int) -> dict:
    station = {
            "network_name": name,
            "channel_number": channel,
            "network_type": "standard",
            "schedule_increment": 30,
            "break_strategy": "standard",
            "commercial_free": True,
            "content_dir": "/media",
    }
    for day in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        station[day] = {}
    return {"station_conf": station}


def create_database(path: Path, started_at: dt.datetime, duration: int) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE catalog_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station TEXT NOT NULL,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            duration REAL NOT NULL,
            tag TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            hints TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            realpath TEXT,
            content_type TEXT DEFAULT 'feature',
            media_type TEXT DEFAULT 'video',
            UNIQUE(station, tag, path)
        );
        CREATE TABLE liquid_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station TEXT NOT NULL,
            liquid_type TEXT NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            break_strategy TEXT NOT NULL,
            title TEXT NOT NULL,
            sequence_key TEXT,
            break_info TEXT,
            content_json TEXT,
            plan_json TEXT NOT NULL
        );
        """
    )
    for entry_id, (station, channel, filename) in enumerate(
        [
            ("Fixture Blue", 42, "channel-42.mp4"),
            ("Fixture Red", 43, "channel-43.mp4"),
        ],
        start=1,
    ):
        media_path = f"/media/{filename}"
        connection.execute(
            """
            INSERT INTO catalog_entries
                (id, station, path, title, duration, tag, realpath,
                 content_type, media_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'feature', 'video')
            """,
            (
                entry_id,
                station,
                media_path,
                f"Channel {channel} Fixture",
                duration,
                "fixture",
                media_path,
            ),
        )
        plan = json.dumps(
            [
                {
                    "path": media_path,
                    "skip": 0,
                    "duration": duration,
                    "is_stream": False,
                    "content_type": "feature",
                    "media_type": "video",
                }
            ]
        )
        connection.execute(
            """
            INSERT INTO liquid_blocks
                (station, liquid_type, start_time, end_time, break_strategy,
                 title, content_json, plan_json)
            VALUES (?, 'LiquidBlock', ?, ?, 'standard', ?, ?, ?)
            """,
            (
                station,
                str(started_at),
                str(started_at + dt.timedelta(seconds=duration)),
                f"Channel {channel} Live Fixture",
                json.dumps(entry_id),
                plan,
            ),
        )
    connection.commit()
    connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--initial-offset", type=int, default=30)
    args = parser.parse_args()

    for name in ("media", "confs", "catalog", "runtime", "logs"):
        (args.root / name).mkdir(parents=True, exist_ok=True)
    generate_media(
        args.root / "media/channel-42.mp4",
        "testsrc",
        440,
        args.duration,
    )
    generate_media(
        args.root / "media/channel-43.mp4",
        "smptebars",
        660,
        args.duration,
    )
    (args.root / "confs/main_config.json").write_text(
        json.dumps({"start_mpv": False})
    )
    (args.root / "confs/channel-42.json").write_text(
        json.dumps(station_config("Fixture Blue", 42))
    )
    (args.root / "confs/channel-43.json").write_text(
        json.dumps(station_config("Fixture Red", 43))
    )
    started_at = dt.datetime.now() - dt.timedelta(seconds=args.initial_offset)
    create_database(
        args.root / "runtime/fs42_fluid.db", started_at, args.duration
    )
    print(
        json.dumps(
            {
                "root": str(args.root),
                "started_at": started_at.isoformat(),
                "duration": args.duration,
            }
        )
    )


if __name__ == "__main__":
    main()
