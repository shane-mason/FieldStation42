import sqlite3
import json


from fs42.station_manager import StationManager
from fs42.catalog_entry import CatalogEntry


class CatalogIO():

    def __init__(self):
        self.db_path = StationManager().server_conf["db_path"]
        self._init_catalog_table()

    def _init_catalog_table(self):
        """
        Creates a database table to hold CatalogEntry records.
        Each record is associated with a station (text string).
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS catalog_entries (
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
                                UNIQUE(station, tag, path)
                                )
                           """)
            
            # Create an index on station for faster queries
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_station 
                             ON catalog_entries(station)""")
            
            # Create an index on tag for faster filtering
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_tag 
                             ON catalog_entries(tag)""")
            
            cursor.close()
    
    def put_catalog_clip_list(self, station_name:str, clip_list):
        flat_list = []

        for tag in clip_list:
            
            try:
                for entry in clip_list[tag]:
                    if isinstance(entry, CatalogEntry):
                        flat_list.append(entry)
                    else:
                        print(f"Warning: Entry {entry} on {tag} is not a CatalogEntry instance. Skipping.")
                        
            except Exception as e:
                print(f"Error processing tag '{tag}': {e}")


        self.put_catalog_entries(station_name, flat_list)

    def put_catalog_entries(self, station_name:str, catalog_entries:list[CatalogEntry]):

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            
            for entry in catalog_entries:
                if isinstance(entry, CatalogEntry):
                    # Convert hints list to JSON string for storage
                    hints = []
                    for hint in entry.hints:
                        hint_json = json.dumps(hint.toJSON()) if entry.hints else None
                        hints.append(hint_json)
                    hints_json = json.dumps(hints) if hints else None


                    # Use INSERT OR REPLACE to overwrite existing entries
                    cursor.execute("""INSERT OR REPLACE INTO catalog_entries 
                                    (station, path, title, duration, tag, count, hints, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                                (station_name, 
                                entry.path, 
                                entry.title, 
                                entry.duration, 
                                entry.tag, 
                                entry.count, 
                                hints_json))
                else:
                    print(f"Warning: Entry {entry} is not a CatalogEntry instance. Skipping.")
                

            
            connection.commit()
            cursor.close()
    
    def get_catalog_entries(self, station_name:str):

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            
            cursor.execute("""SELECT path, title, duration, tag, count, hints 
                             FROM catalog_entries 
                             WHERE station = ?
                             ORDER BY tag, title""", (station_name,))
            
            rows = cursor.fetchall()
            cursor.close()
            
            catalog_entries = []
            for row in rows:
                # Create CatalogEntry object
                entry = CatalogEntry.from_db_row(row)
                catalog_entries.append(entry)
            
            return catalog_entries
        
    def get_catalog_clip_list(self, station_name: str):

        catalog_entries = self.get_catalog_entries(station_name)
        clip_list = {}
        
        for entry in catalog_entries:
            if entry.tag not in clip_list:
                clip_list[entry.tag] = []
            clip_list[entry.tag].append(entry)
        
        return clip_list


    def delete_all_entries_for_station(self, station_name: str):

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""DELETE FROM catalog_entries WHERE station = ?""", (station_name,))
            connection.commit()
            cursor.close()

    def get_entry_by_path(self, station_name: str, path: str):

        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""SELECT * FROM catalog_entries 
                              WHERE station = ? AND path = ?""", (station_name, path))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                (_id, station, path, title, duration, tag, count, hints_str, created_at, updated_at) = row
                return CatalogEntry(path, duration, tag, json.loads(hints_str) if hints_str else [], count=count)
                
            return None
        
    def get_by_tag(self, station_name: str, tag: str):
        """
        Retrieves all catalog entries for a specific tag.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""SELECT * FROM catalog_entries 
                              WHERE station = ? AND tag = ?""", (station_name, tag))
            rows = cursor.fetchall()
            cursor.close()
            
            catalog_entries = []
            for row in rows:
                (_id, station, path, title, duration, tag, count, hints_str, created_at, updated_at) = row
                catalog_entries.append(CatalogEntry(path, duration, tag, json.loads(hints_str) if hints_str else [], count=count))
                
            return catalog_entries