import sqlite3  

from fs42.station_manager import StationManager
from fs42.sequence import NamedSequence, SequenceEntry

class SequenceIO:
    def __init__(self):
        self.db_path = StationManager().server_conf["db_path"]
        self._init_sequence_table()


    def _init_sequence_table(self):
        """
        Creates a database table to hold SeriesIndex records.
        Each record is associated with a series (text string).
        """
        with sqlite3.connect(self.db_path) as connection:
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
            
            # now make a table to hold sequence entries
            cursor.execute("""CREATE TABLE IF NOT EXISTS sequence_entries (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                fpath TEXT NOT NULL,
                                sequence_index INTEGER NOT NULL,
                                named_sequence_id INTEGER NOT NULL,
                                FOREIGN KEY(named_sequence_id) REFERENCES named_sequence(id)
                            )""")
            cursor.close()
            connection.commit()

    def put_sequence(self,  station_name: str, named_sequence):
        """
        Store a SeriesIndex in the database.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            # Insert or update the named sequence
            cursor.execute("""INSERT OR REPLACE INTO named_sequence 
                              (station, sequence_name, tag_path, start_perc, end_perc, current_index) 
                              VALUES (?, ?, ?, ?, ?, ?)""",
                           (station_name, named_sequence.sequence_name, named_sequence.tag_path,
                            named_sequence.start_perc, named_sequence.end_perc, named_sequence.current_index))
            named_sequence_id = cursor.lastrowid
            
            # Now insert the sequence entries
            for index, entry in enumerate(named_sequence.episodes):
                cursor.execute("""INSERT INTO sequence_entries (fpath, sequence_index, named_sequence_id) 
                                  VALUES (?, ?, ?)""",
                               (entry.fpath, index, named_sequence_id))
            
            connection.commit()


    def get_sequence(self, station_name: str, sequence_name: str, tag_path: str) -> NamedSequence:

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""SELECT id, start_perc, end_perc, current_index 
                              FROM named_sequence 
                              WHERE station = ? AND sequence_name = ? AND tag_path = ?""",
                           (station_name, sequence_name, tag_path))
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            named_sequence_id, start_perc, end_perc, current_index = row
            
            # Now retrieve the sequence entries
            cursor.execute("""SELECT fpath FROM sequence_entries 
                              WHERE named_sequence_id = ? ORDER BY sequence_index""",
                           (named_sequence_id,))
            file_paths = [row[0] for row in cursor.fetchall()]
            

            ns = NamedSequence(station_name, sequence_name, tag_path, start_perc, end_perc, current_index, file_paths)
 
            return ns

    # a function to delete all sequences for a station
    def delete_sequences_for_station(self, station_name: str):
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            # Delete all sequence entries for the station
            cursor.execute("""DELETE FROM sequence_entries 
                              WHERE named_sequence_id IN 
                              (SELECT id FROM named_sequence WHERE station = ?)""",
                           (station_name,))
            # Delete the named sequences for the station
            cursor.execute("""DELETE FROM named_sequence WHERE station = ?""", (station_name,))
            connection.commit()

    # make a function to update the current index of a sequence
    def update_current_index(self, station_name: str, sequence_name: str, tag_path: str, new_index: int):
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""UPDATE named_sequence 
                              SET current_index = ? 
                              WHERE station = ? AND sequence_name = ? AND tag_path = ?""",
                           (new_index, station_name, sequence_name, tag_path))
            cursor.close()
            connection.commit()

    
