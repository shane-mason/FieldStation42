import sqlite3
import json
from datetime import datetime
from fs42.station_manager import StationManager
from fs42.liquid_blocks import LiquidBlock, LiquidLoopBlock, LiquidClipBlock, LiquidOffAirBlock
from fs42.block_plan import BlockPlanEntry
from fs42.catalog_api import CatalogAPI
from fs42.title_parser import TitleParser


class LiquidIO:
    """
    LiquidIO is a class that handles the input and output of liquid data.
    It provides methods to read and write liquid data to a database.
    """

    def __init__(self):
        self.db_path = StationManager().server_conf["db_path"]
        self._init_liquid_table()

    def _init_liquid_table(self):
        """
        Creates a database table to hold liquid data.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS liquid_blocks (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                station TEXT NOT NULL,
                                liquid_type TEXT NOT NULL,
                                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                break_strategy TEXT NOT NULL,
                                title TEXT NOT NULL,
                                sequence_key TEXT,
                                break_info TEXT,
                                content_json TEXT NOT NULL,
                                plan_json TEXT NOT NULL
                            )""")

            # Create indexes for performance
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_liquid_blocks_station
                            ON liquid_blocks(station)""")
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_liquid_blocks_station_time
                            ON liquid_blocks(station, start_time, end_time)""")

            cursor.close()
            connection.commit()

    def get_liquid_blocks(self, station_name: str) -> list[LiquidBlock]:
        """
        Retrieve liquid blocks from the database for a given station.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM liquid_blocks WHERE station = ? ORDER BY start_time", (station_name,))
            rows = cursor.fetchall()
            cursor.close()

            # Collect all content IDs for batch lookup
            content_ids = set()
            for row in rows:
                content_json = json.loads(row[9]) if row[9] else None
                if content_json:
                    if isinstance(content_json, list):
                        content_ids.update(content_json)
                    else:
                        content_ids.add(content_json)

            # Batch fetch all content entries
            content_cache = CatalogAPI.get_entries_by_ids(list(content_ids)) if content_ids else {}

            # Build blocks with cached content
            liquid_blocks = []
            for row in rows:
                block = LiquidIO._build_block_from_row(row, content_cache)
                liquid_blocks.append(block)

            return liquid_blocks

    def query_liquid_blocks(self, station_name: str, start: str, end: str) -> list[LiquidBlock]:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT * FROM liquid_blocks WHERE station = ? AND start_time < ? AND end_time > ? ORDER BY start_time",
                (station_name, end, start),
            )
            rows = cursor.fetchall()
            cursor.close()

            # Collect all content IDs for batch lookup
            content_ids = set()
            for row in rows:
                content_json = json.loads(row[9]) if row[9] else None
                if content_json:
                    if isinstance(content_json, list):
                        content_ids.update(content_json)
                    else:
                        content_ids.add(content_json)

            # Batch fetch all content entries
            content_cache = CatalogAPI.get_entries_by_ids(list(content_ids)) if content_ids else {}

            # Build blocks with cached content
            liquid_blocks = []
            for row in rows:
                block = LiquidIO._build_block_from_row(row, content_cache)
                liquid_blocks.append(block)

            return liquid_blocks

    def put_liquid_blocks(self, station_name: str, liquid_blocks: list[LiquidBlock]):
        """
        Store liquid blocks in the database.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()

            for block in liquid_blocks:

                if block.content and not isinstance(block.content, list):
                    content_json = json.dumps(block.content.dbid)

                elif block.content:
                    content_json = json.dumps([c.dbid for c in block.content])
                else:
                    content_json = None


                # plan_json = json.dumps(block.plan.toJSON()) if block.plan else None
                plan_json = json.dumps([p.toJSON() for p in block.plan])
                block_type = type(block).__name__
                break_info = json.dumps(block.break_info) if block.break_info else None
                seq_json = json.dumps(block.sequence_key) if block.sequence_key else None
               
                cursor.execute(
                    """INSERT OR REPLACE INTO liquid_blocks 
                       (station, liquid_type, start_time, end_time, break_strategy, title, sequence_key, break_info, content_json, plan_json) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        station_name,
                        block_type,
                        block.start_time,
                        block.end_time,
                        block.break_strategy,
                        block.title,
                        seq_json,
                        break_info,
                        content_json,
                        plan_json,
                    ),
                )
            cursor.close()
            connection.commit()

    def delete_liquid_blocks(self, station_name: str):
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM liquid_blocks WHERE station = ?", (station_name,))
            cursor.close()
            connection.commit()

    @staticmethod
    def _build_block_from_row(row, content_cache: dict = None):
        """
        Helper method to build a LiquidBlock from a database row.
        If content_cache is provided, uses it for batch lookups instead of individual CatalogAPI calls.
        """
        _id = row[0]
        _station = row[1]
        _liquid_type = row[2]
        _start_time = datetime.fromisoformat(row[3])
        _end_time = datetime.fromisoformat(row[4])
        _break_strategy = row[5]
        _title = row[6]
        _sequence_key = json.loads(row[7]) if row[7] else None
        _break_info = json.loads(row[8]) if row[8] else None 
        _content_json = json.loads(row[9]) if row[9] else None
        _plan_json = json.loads(row[10]) if row[10] else []
    

        content_obj = None
        if _content_json:
            if not isinstance(_content_json, list):
                # Single content entry
                if content_cache is not None:
                    content_obj = content_cache.get(int(_content_json))
                else:
                    content_obj = CatalogAPI.get_entry_by_id(int(_content_json))
            else:
                # Multiple content entries
                content_obj = []
                for entry in _content_json:
                    if content_cache is not None:
                        cached_entry = content_cache.get(int(entry))
                        if cached_entry:
                            content_obj.append(cached_entry)
                    else:
                        content_obj.append(CatalogAPI.get_entry_by_id(int(entry)))  

        main_normal = StationManager().server_conf.get("normalize_titles", True)
        the_title = _title

        if main_normal:
            the_title = TitleParser.parse_title(the_title)

        args = (
            content_obj,
            _start_time,
            _end_time,
            the_title,  # title
            _break_strategy,  # break_strategy
            _break_info,
        )

        block = LiquidIO._block_factory(_liquid_type, args)
        block.sequence_key = _sequence_key

        plans = []
        for p in _plan_json:
            plans.append(BlockPlanEntry(p["path"], p["skip"], p["duration"], p["is_stream"]))
        block.plan = plans
        return block

    @staticmethod
    def _block_factory(liquid_type, args):
        match liquid_type:
            case "LiquidBlock":
                return LiquidBlock(*args)
            case "LiquidOffAirBlock":
                return LiquidOffAirBlock(*args)
            case "LiquidClipBlock":
                return LiquidClipBlock(*args)
            case "LiquidLoopBlock":
                return LiquidLoopBlock(*args)
            case _:
                raise ValueError(f"Unknown liquid type: {liquid_type}")

    def search_liquid_blocks(self, station_name: str, query: str) -> list[LiquidBlock]:
        """
        Search liquid blocks by title for a given station.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT * FROM liquid_blocks WHERE station = ? AND title LIKE ? ORDER BY start_time", 
                (station_name, f"%{query}%")
            )
            rows = cursor.fetchall()
            cursor.close()

        blocks = []
        for row in rows:
            blocks.append(LiquidIO._build_block_from_row(row))

        return blocks

    def search_all_liquid_blocks(self, query: str) -> dict:
        """
        Search liquid blocks by title across all stations.
        Returns a dictionary with station names as keys and lists of blocks as values.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT * FROM liquid_blocks WHERE title LIKE ? ORDER BY station, start_time", 
                (f"%{query}%",)
            )
            rows = cursor.fetchall()
            cursor.close()

        results = {}
        for row in rows:
            station = row[1]  # station is at index 1
            if station not in results:
                results[station] = []
            results[station].append(LiquidIO._build_block_from_row(row))

        return results
