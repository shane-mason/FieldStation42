import logging
import sqlite3
import datetime
import os
from fs42.media_processor import MediaProcessor
from fs42.fluid_objects import FileRepoEntry


class FluidStatements:
    """Basic static SQL functions for interacting with the Fluid catalog DB"""

    @staticmethod
    def check_file_cache(connection: sqlite3.Connection, full_path) -> FileRepoEntry:
        """Find full_path and return fullpath if its in the file cache"""

        cursor = connection.cursor()
        cursor.execute("SELECT * FROM file_meta WHERE path = ?;", (full_path,))
        row = cursor.fetchone()
        result = None
        if row:
            repo_entry = FileRepoEntry(row)
            result = repo_entry
        cursor.close()
        return result

    @staticmethod
    def iterate_file_entries(connection: sqlite3.Connection, entries: list[FileRepoEntry]) -> None:
        """Takes a list of file entries, determines if they are cached and adds them if not."""

        cursor = connection.cursor()
        for entry in entries:
            # see if there is an entry already
            cursor.execute("SELECT * FROM file_meta WHERE path = ?;", (entry.path,))
            row = cursor.fetchone()
            if row:
                repo_entry = FileRepoEntry()
                repo_entry.from_db_row(row)

                # compare it to the stats in the repo
                if entry != repo_entry:
                    # then the stats match
                    FluidStatements.update_file_entry(connection, entry)

            else:
                FluidStatements.add_file_entry(connection, entry)
        cursor.close()

    @staticmethod
    def trim_file_entries(connection: sqlite3.Connection, older_than: datetime):
        """Checks all files in the cache to ensure still on disk and removes them if not."""

        cursor = connection.cursor()
        cursor.execute("SELECT * FROM file_meta WHERE last_updated < ?;", (older_than,))
        to_remove = []
        rows = cursor.fetchall()
        logging.getLogger("FLUID").info(f"Checking {len(rows)} files on the filesystem")
        for row in rows:
            repo_entry = FileRepoEntry()
            repo_entry.from_db_row(row)
            if not os.path.exists(repo_entry.path):
                logging.getLogger("FLUID").info(f"File not found on filesystem - will remove: {repo_entry}")
                to_remove.append(repo_entry.path)

        connection.execute("BEGIN TRANSACTION;")

        for p in to_remove:
            cursor.execute("DELETE from file_meta WHERE path=?", (p,))

        cursor.close()
        connection.commit()

    @staticmethod
    def update_file_entry(connection: sqlite3.Connection, entry: FileRepoEntry):
        """An old entry has changed, get the new stats and update it."""
        cursor = connection.cursor()
        now = datetime.datetime.now()

        processed = MediaProcessor.process_one(entry.path, "processing", [])
        if not processed:
            return False
        entry.duration = processed.duration

        logging.getLogger("FLUID").info(f"Updating existing file entry: {entry.path}")

        update = """UPDATE file_meta SET duration=?, size=?, last_mod=?, last_updated=?, last_checked=? 
        WHERE path=?;
        """
        values = (entry.duration, entry.size, entry.last_mod, now, now, entry.path)
        cursor.execute(update, values)
        cursor.close()
        connection.commit()

    @staticmethod
    def add_file_entry(connection: sqlite3.Connection, entry: FileRepoEntry):
        """This file isn't in the cache - add it."""
        cursor = connection.cursor()
        now = datetime.datetime.now()

        entry.first_added = now
        entry.last_checked = now
        entry.last_upates = now

        processed = MediaProcessor.process_one(entry.path, "processing", [])
        if not processed:
            return False

        entry.duration = processed.duration

        logging.getLogger("FLUID").info(f"Caching new file entry: {entry}")

        cursor.execute("INSERT INTO file_meta VALUES (?, ?, ?, ?, ?, ?, ?, ?);", entry.to_db_row())
        cursor.close()
        connection.commit()

    @staticmethod
    def init_db(connection: sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS file_meta ( 
                            path TEXT PRIMARY KEY,
                            duration REAL,
                            size INTEGER,
                            first_added TIMESTAMP,
                            last_mod TIMESTAMP,
                            last_checked TIMESTAMP,
                            last_updated TIMESTAMP,
                            meta TEXT
                            )
                            """)

        cursor.close()
