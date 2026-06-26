import sqlite3
from contextlib import contextmanager

from fs42.station_manager import StationManager
from fs42.sequence import NamedSequence


class SequenceIO:
    def __init__(self):
        self.db_path = StationManager().server_conf["db_path"]
        self._init_sequence_table()

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

    def _init_sequence_table(self):
        """
        Creates a database table to hold SeriesIndex records.
        Each record is associated with a series (text string).
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS named_sequence (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                station TEXT NOT NULL,
                                sequence_name TEXT NOT NULL,
                                tag_path TEXT NOT NULL,
                                start_perc REAL NOT NULL,
                                end_perc REAL NOT NULL,
                                current_index INTEGER NOT NULL,
                                UNIQUE(station, sequence_name, tag_path)
                            )""")
            try:
                cursor.execute("ALTER TABLE named_sequence ADD COLUMN parent_tag TEXT")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
                
            # now make a table to hold sequence entries
            cursor.execute("""CREATE TABLE IF NOT EXISTS sequence_entries (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                fpath TEXT NOT NULL,
                                sequence_index INTEGER NOT NULL,
                                named_sequence_id INTEGER NOT NULL,
                                FOREIGN KEY(named_sequence_id) REFERENCES named_sequence(id)
                            )""")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sequence_group_state (
                    station TEXT NOT NULL,
                    sequence_name TEXT NOT NULL,
                    parent_tag TEXT NOT NULL,
                    active_tag_path TEXT NOT NULL,
                    PRIMARY KEY (
                        station,
                        sequence_name,
                        parent_tag
                    )
                )
            """)
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sequence_entries_named_sequence
            ON sequence_entries(named_sequence_id)
            """)

            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sequence_entries_lookup
            ON sequence_entries(named_sequence_id, sequence_index)
            """)

            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_named_sequence_station
            ON named_sequence(station)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_named_sequence_parent
            ON named_sequence(station, sequence_name, parent_tag)
            """)
            cursor.close()
            connection.commit()

    def put_sequence(self, station_name: str, named_sequence):
        """
        Store a SeriesIndex in the database
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO named_sequence
                    (station, sequence_name, tag_path, start_perc, end_perc, current_index, parent_tag)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station, sequence_name, tag_path)
                DO UPDATE SET
                    start_perc = excluded.start_perc,
                    end_perc = excluded.end_perc,
                    current_index = excluded.current_index,
                    parent_tag = excluded.parent_tag
                """,
                (
                    station_name,
                    named_sequence.sequence_name,
                    named_sequence.tag_path,
                    named_sequence.start_perc,
                    named_sequence.end_perc,
                    named_sequence.current_index,
                    getattr(named_sequence, "parent_tag", None),
                ),
            )

            # stable ID lookup
            cursor.execute(
                """
                SELECT id FROM named_sequence
                WHERE station = ? AND sequence_name = ? AND tag_path = ?
                """,
                (station_name, named_sequence.sequence_name, named_sequence.tag_path),
            )

            row = cursor.fetchone()
            if not row:
                raise RuntimeError("UPSERT failed to return sequence id")

            named_sequence_id = row[0]

            # Replace entries
            cursor.execute(
                "DELETE FROM sequence_entries WHERE named_sequence_id = ?",
                (named_sequence_id,),
            )

            for index, entry in enumerate(named_sequence.episodes):
                cursor.execute(
                    """
                    INSERT INTO sequence_entries
                        (fpath, sequence_index, named_sequence_id)
                    VALUES (?, ?, ?)
                    """,
                    (entry.fpath, index, named_sequence_id),
                )

            connection.commit()

    def get_sequence(self, station_name: str, sequence_name: str, tag_path: str) -> NamedSequence:
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT id, start_perc, end_perc, current_index 
                              FROM named_sequence 
                              WHERE station = ? AND sequence_name = ? AND tag_path = ?""",
                (station_name, sequence_name, tag_path),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            named_sequence_id, start_perc, end_perc, current_index = row

            # Now retrieve the sequence entries
            cursor.execute(
                """SELECT fpath FROM sequence_entries 
                              WHERE named_sequence_id = ? ORDER BY sequence_index""",
                (named_sequence_id,),
            )
            file_paths = [row[0] for row in cursor.fetchall()]

            ns = NamedSequence(station_name, sequence_name, tag_path, start_perc, end_perc, current_index, file_paths)

            return ns

    def get_all_sequences_for_station(self, station_name: str) -> list[NamedSequence]:
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT id, sequence_name, tag_path, start_perc, end_perc, current_index 
                              FROM named_sequence 
                              WHERE station = ?""",
                (station_name,),
            )
            rows = cursor.fetchall()

            if not rows:
                return []

            sequences = []
            for row in rows:
                named_sequence_id, sequence_name, tag_path, start_perc, end_perc, current_index = row

                # Now retrieve the sequence entries for this sequence
                cursor.execute(
                    """SELECT fpath FROM sequence_entries 
                                  WHERE named_sequence_id = ? ORDER BY sequence_index""",
                    (named_sequence_id,),
                )
                file_paths = [entry_row[0] for entry_row in cursor.fetchall()]

                ns = NamedSequence(station_name, sequence_name, tag_path, start_perc, end_perc, current_index, file_paths)
                sequences.append(ns)

            return sequences


    def delete_sequences_for_station(self, station_name: str):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            # Delete all sequence entries for the station
            cursor.execute(
                """DELETE FROM sequence_entries 
                              WHERE named_sequence_id IN 
                              (SELECT id FROM named_sequence WHERE station = ?)""",
                (station_name,),
            )
            # Delete the named sequences for the station
            cursor.execute("""DELETE FROM named_sequence WHERE station = ?""", (station_name,))
            connection.commit()

    def delete_sequence(self,station_name,sequence_name,tag_path):
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT id
                FROM named_sequence
                WHERE station = ?
                  AND sequence_name = ?
                  AND tag_path = ?
            """, (
                station_name,
                sequence_name,
                tag_path
            ))

            row = cursor.fetchone()

            if not row:
                return

            sequence_id = row[0]

            cursor.execute(
                """
                DELETE FROM sequence_entries
                WHERE named_sequence_id = ?
                """,
                (sequence_id,)
            )

            cursor.execute(
                """
                DELETE FROM named_sequence
                WHERE id = ?
                """,
                (sequence_id,)
            )

            connection.commit()
    
    def update_current_index(self, station_name: str, sequence_name: str, tag_path: str, new_index: int):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE named_sequence 
                              SET current_index = ? 
                              WHERE station = ? AND sequence_name = ? AND tag_path = ?""",
                (new_index, station_name, sequence_name, tag_path),
            )
            cursor.close()
            connection.commit()

    def update_sequence_index_by_path(self, station_name: str, sequence_name: str, tag_path: str, episode_path: str):
        with self._get_connection() as connection:
            cursor = connection.cursor()
            # Get the sequence_index for the episode_path
            cursor.execute("""
                SELECT se.sequence_index 
                FROM sequence_entries se
                JOIN named_sequence ns ON se.named_sequence_id = ns.id
                WHERE ns.station = ? AND ns.sequence_name = ? AND ns.tag_path = ? AND se.fpath = ?
            """, (station_name, sequence_name, tag_path, episode_path))
            
            result = cursor.fetchone()
            if result:
                new_index = result[0]
                cursor.execute("""
                    UPDATE named_sequence 
                    SET current_index = ? 
                    WHERE station = ? AND sequence_name = ? AND tag_path = ?
                """, (new_index, station_name, sequence_name, tag_path))
                connection.commit()
                return True
            return False

    def update_sequence_entries(self, station_name: str, sequence_name: str, tag_path: str, file_list: list, current_file: str, fallback_index: int):
        """
        Replace sequence entries with a new file list while preserving playback position.
        - If current_file is still in the new list, current_index moves to its new sorted position.
        - If current_file is gone but fallback_index is still in bounds, keep it (different file is there now).
        - If fallback_index is out of bounds, reset to 0.
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute(
                "SELECT id FROM named_sequence WHERE station = ? AND sequence_name = ? AND tag_path = ?",
                (station_name, sequence_name, tag_path),
            )
            row = cursor.fetchone()
            if not row:
                return

            named_sequence_id = row[0]
            sorted_files = sorted(str(f) for f in file_list)

            import logging
            _l = logging.getLogger("SEQUENCE")
            if current_file and current_file in sorted_files:
                new_index = sorted_files.index(current_file)
                _l.debug(f"update_sequence_entries: current file still present, index {fallback_index} -> {new_index} ({sorted_files[new_index]})")
            elif fallback_index < len(sorted_files):
                new_index = fallback_index
                _l.debug(f"update_sequence_entries: current file removed, keeping index {new_index} (now points to {sorted_files[new_index]})")
            else:
                new_index = 0
                _l.debug(f"update_sequence_entries: index {fallback_index} out of bounds for {len(sorted_files)} files, resetting to 0")

            cursor.execute("DELETE FROM sequence_entries WHERE named_sequence_id = ?", (named_sequence_id,))

            for idx, fpath in enumerate(sorted_files):
                cursor.execute(
                    "INSERT INTO sequence_entries (fpath, sequence_index, named_sequence_id) VALUES (?, ?, ?)",
                    (fpath, idx, named_sequence_id),
                )

            cursor.execute(
                "UPDATE named_sequence SET current_index = ? WHERE id = ?",
                (new_index, named_sequence_id),
            )
            connection.commit()

    def clean_sequences(self):
        """
        Clean up sequences by removing entries that are no longer valid.
        This can be used to remove entries that have been deleted from the filesystem.
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """DELETE FROM sequence_entries
                        WHERE NOT EXISTS (
                            SELECT 1 FROM named_sequence
                            WHERE named_sequence.id = sequence_entries.named_sequence_id
                        );"""
            )
            connection.commit()
            cursor.close()

    def get_active_sequence(
        self,
        station_name,
        sequence_name,
        parent_tag
    ):
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT active_tag_path
                FROM sequence_group_state
                WHERE station = ?
                  AND sequence_name = ?
                  AND parent_tag = ?
            """, (
                station_name,
                sequence_name,
                parent_tag
            ))

            row = cursor.fetchone()

            return row[0] if row else None
            
    def set_active_sequence(
        self,
        station_name,
        sequence_name,
        parent_tag,
        active_tag_path
    ):
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO sequence_group_state
                (
                    station,
                    sequence_name,
                    parent_tag,
                    active_tag_path
                )
                VALUES (?, ?, ?, ?)
            """, (
                station_name,
                sequence_name,
                parent_tag,
                active_tag_path
            ))
            connection.commit()
            
    def get_all_active_sequences(
        self,
        station_name
    ):
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT active_tag_path
                FROM sequence_group_state
                WHERE station = ?
            """, (
                station_name,
            ))

            return [
                r[0]
                for r in cursor.fetchall()
            ]
            
    def get_child_sequences(
        self,
        station_name,
        sequence_name,
        parent_tag
    ):
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT tag_path
                FROM named_sequence
                WHERE station = ?
                  AND sequence_name = ?
                  AND tag_path LIKE ?
            """, (
                station_name,
                sequence_name,
                f"{parent_tag}/%"
            ))

            return [r[0] for r in cursor.fetchall()]