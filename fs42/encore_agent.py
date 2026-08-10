import datetime
import re
import sqlite3
from contextlib import contextmanager

from fs42.catalog import MatchingContentNotFound
from fs42.catalog_api import CatalogAPI
from fs42.station_manager import StationManager


class EncoreUnavailable(MatchingContentNotFound):
    pass


class EncoreAgent:
    def __init__(self, station_config, catalog=None):
        self.station_config = station_config
        self.station = station_config["network_name"]
        self.catalog = catalog
        self.db_path = StationManager().server_conf["db_path"]
        self._pending_airings = []
        self._pending_cursors = {}
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_tables(self):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS airing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT NOT NULL,
                    airing_id TEXT NOT NULL,
                    source_start_time TIMESTAMP NOT NULL,
                    content_id INTEGER,
                    content_path TEXT NOT NULL,
                    title TEXT,
                    tag TEXT,
                    UNIQUE(station, airing_id, source_start_time)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_airing_history_lookup
                ON airing_history(station, airing_id, source_start_time)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS encore_cursor (
                    station TEXT NOT NULL,
                    cursor_name TEXT NOT NULL,
                    source_airing_id TEXT NOT NULL,
                    last_source_start_time TIMESTAMP,
                    PRIMARY KEY (
                        station,
                        cursor_name,
                        source_airing_id
                    )
                )
            """)

    def record_airing(self, airing_id, block):
        if not airing_id or not block or not block.content or isinstance(block.content, list):
            return

        self._pending_airings.append({
            "station": self.station,
            "airing_id": airing_id,
            "source_start_time": block.start_time,
            "content_id": block.content.dbid,
            "content_path": block.content.path,
            "title": block.content.title,
            "tag": block.content.tag,
        })

    def resolve(self, encore_config, current_mark):
        strategy = encore_config.get("strategy", "offset")
        source = encore_config.get("source")
        if not source:
            raise EncoreUnavailable("Encore source is required")

        if strategy == "offset":
            offset = self._parse_offset(encore_config.get("offset"))
            source_time = current_mark - offset
            row = self._find_airing_at(source, source_time)
            if not row:
                raise EncoreUnavailable(
                    f"No encore source airing for {source} at {source_time}"
                )
            return self._content_from_airing(row), {
                "source": source,
                "strategy": "offset",
                "source_start_time": row["source_start_time"].isoformat(),
            }

        if strategy == "queue":
            cursor_name = encore_config.get("cursor")
            if not cursor_name:
                raise EncoreUnavailable("Queue encore cursor is required")

            last_source_start = self._get_effective_cursor(cursor_name, source)
            row = self._find_next_airing(source, current_mark, last_source_start)
            if not row:
                raise EncoreUnavailable(
                    f"No unconsumed encore source airing for {source} before {current_mark}"
                )

            self._pending_cursors[(cursor_name, source)] = row["source_start_time"]
            return self._content_from_airing(row), {
                "source": source,
                "strategy": "queue",
                "cursor": cursor_name,
                "source_start_time": row["source_start_time"].isoformat(),
            }

        raise EncoreUnavailable(f"Unknown encore strategy: {strategy}")

    def commit(self):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            for airing in self._pending_airings:
                cursor.execute("""
                    INSERT INTO airing_history
                        (station, airing_id, source_start_time, content_id, content_path, title, tag)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(station, airing_id, source_start_time)
                    DO UPDATE SET
                        content_id = excluded.content_id,
                        content_path = excluded.content_path,
                        title = excluded.title,
                        tag = excluded.tag
                """, (
                    airing["station"],
                    airing["airing_id"],
                    airing["source_start_time"].isoformat(),
                    airing["content_id"],
                    airing["content_path"],
                    airing["title"],
                    airing["tag"],
                ))

            for (cursor_name, source), source_start_time in self._pending_cursors.items():
                cursor.execute("""
                    INSERT INTO encore_cursor
                        (station, cursor_name, source_airing_id, last_source_start_time)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(station, cursor_name, source_airing_id)
                    DO UPDATE SET
                        last_source_start_time = excluded.last_source_start_time
                """, (self.station, cursor_name, source, source_start_time.isoformat()))

        self._pending_airings = []
        self._pending_cursors = {}

    @staticmethod
    def reset_cursors_from_blocks(station_config, blocks, cutoff):
        agent = EncoreAgent(station_config)
        retained = {}
        known = agent._get_cursor_keys()

        for block in blocks:
            key = getattr(block, "encore_key", None)
            if not key or key.get("strategy") != "queue":
                continue
            cursor_name = key.get("cursor")
            source = key.get("source")
            source_start = key.get("source_start_time")
            if not cursor_name or not source or not source_start:
                continue
            known.add((cursor_name, source))
            if block.start_time >= cutoff:
                continue
            parsed = datetime.datetime.fromisoformat(source_start)
            current = retained.get((cursor_name, source))
            if current is None or parsed > current:
                retained[(cursor_name, source)] = parsed

        with agent._get_connection() as connection:
            cursor = connection.cursor()
            for cursor_name, source in known:
                cursor.execute("""
                    INSERT INTO encore_cursor
                        (station, cursor_name, source_airing_id, last_source_start_time)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(station, cursor_name, source_airing_id)
                    DO UPDATE SET
                        last_source_start_time = excluded.last_source_start_time
                """, (
                    agent.station,
                    cursor_name,
                    source,
                    (
                        retained[(cursor_name, source)].isoformat()
                        if (cursor_name, source) in retained
                        else None
                    ),
                ))

    def _get_cursor_keys(self):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT cursor_name, source_airing_id
                FROM encore_cursor
                WHERE station = ?
            """, (self.station,))
            return set(cursor.fetchall())

    def _get_effective_cursor(self, cursor_name, source):
        pending = self._pending_cursors.get((cursor_name, source))
        if pending:
            return pending

        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT last_source_start_time
                FROM encore_cursor
                WHERE station = ?
                  AND cursor_name = ?
                  AND source_airing_id = ?
            """, (self.station, cursor_name, source))
            row = cursor.fetchone()
            if row and row[0]:
                return datetime.datetime.fromisoformat(row[0])
        return None

    def _find_airing_at(self, source, source_time):
        for airing in reversed(self._pending_airings):
            if (
                airing["airing_id"] == source
                and airing["source_start_time"] == source_time
            ):
                return airing

        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT content_id, content_path, title, tag, source_start_time
                FROM airing_history
                WHERE station = ?
                  AND airing_id = ?
                  AND source_start_time = ?
            """, (self.station, source, source_time.isoformat()))
            row = cursor.fetchone()
            return self._row_to_airing(row) if row else None

    def _find_next_airing(self, source, encore_start, last_source_start):
        candidates = {}
        with self._get_connection() as connection:
            cursor = connection.cursor()
            if last_source_start is None:
                cursor.execute("""
                    SELECT content_id, content_path, title, tag, source_start_time
                    FROM airing_history
                    WHERE station = ?
                      AND airing_id = ?
                      AND source_start_time < ?
                    ORDER BY source_start_time
                """, (self.station, source, encore_start.isoformat()))
            else:
                cursor.execute("""
                    SELECT content_id, content_path, title, tag, source_start_time
                    FROM airing_history
                    WHERE station = ?
                      AND airing_id = ?
                      AND source_start_time > ?
                      AND source_start_time < ?
                    ORDER BY source_start_time
                """, (
                    self.station,
                    source,
                    last_source_start.isoformat(),
                    encore_start.isoformat(),
                ))
            for row in cursor.fetchall():
                airing = self._row_to_airing(row)
                candidates[airing["source_start_time"]] = airing

        for airing in self._pending_airings:
            if airing["airing_id"] != source:
                continue
            if airing["source_start_time"] >= encore_start:
                continue
            if last_source_start and airing["source_start_time"] <= last_source_start:
                continue
            candidates[airing["source_start_time"]] = airing

        if not candidates:
            return None
        ordered = sorted(candidates.values(), key=lambda airing: airing["source_start_time"])
        return ordered[0]

    def _content_from_airing(self, airing):
        content = None
        if airing.get("content_id"):
            content = CatalogAPI.get_entry_by_id(int(airing["content_id"]))
        if content is None and self.catalog is not None:
            content = self.catalog.entry_by_fpath(airing["content_path"])
        if content is None:
            content = CatalogAPI.get_by_path(self.station_config, airing["content_path"])
        if content is None:
            raise EncoreUnavailable(
                f"Encore source content is no longer in the catalog: {airing['content_path']}"
            )
        return content

    @staticmethod
    def _row_to_airing(row):
        content_id, content_path, title, tag, source_start_time = row
        return {
            "content_id": content_id,
            "content_path": content_path,
            "title": title,
            "tag": tag,
            "source_start_time": datetime.datetime.fromisoformat(source_start_time),
        }

    @staticmethod
    def _parse_offset(offset):
        if isinstance(offset, datetime.timedelta):
            return offset
        if not isinstance(offset, str):
            raise EncoreUnavailable("Encore offset must be a string such as '12h'")

        match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", offset)
        if not match:
            raise EncoreUnavailable(f"Invalid encore offset: {offset}")

        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return datetime.timedelta(seconds=amount)
        if unit == "m":
            return datetime.timedelta(minutes=amount)
        if unit == "h":
            return datetime.timedelta(hours=amount)
        return datetime.timedelta(days=amount)
