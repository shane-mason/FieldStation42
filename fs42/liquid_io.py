import sqlite3
import json
from datetime import datetime
from fs42.station_manager import StationManager
from fs42.liquid_blocks import LiquidBlock, LiquidLoopBlock, LiquidClipBlock, LiquidOffAirBlock
from fs42.block_plan import BlockPlanEntry
from fs42.catalog_entry import CatalogEntry


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
                                break_info TEXT,
                                content_json TEXT NOT NULL,
                                plan_json TEXT NOT NULL
                            )""")
            cursor.close()
            connection.commit()

    def get_liquid_blocks(self, station_name: str) -> list[LiquidBlock]:
        """
        Retrieve liquid blocks from the database for a given station.
        """
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM liquid_blocks WHERE station = ?", (station_name,))
            rows = cursor.fetchall()
            cursor.close()

            liquid_blocks = []
            for row in rows:
                block = LiquidIO._build_block_from_row(row)
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
                    content_json = json.dumps(block.content.toJSON())
                elif block.content:
                    content_json = json.dumps([c.toJSON() for c in block.content])
                else:
                    content_json = None

                # plan_json = json.dumps(block.plan.toJSON()) if block.plan else None
                plan_json = json.dumps([p.toJSON() for p in block.plan])
                block_type = type(block).__name__

                break_info = json.dumps(block.break_info) if block.break_info else None

                cursor.execute(
                    """INSERT OR REPLACE INTO liquid_blocks 
                       (station, liquid_type, start_time, end_time, break_strategy, title, break_info, content_json, plan_json) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        station_name,
                        block_type,
                        block.start_time,
                        block.end_time,
                        block.break_strategy,
                        block.title,
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
    def _build_block_from_row(row):
        """
        Helper method to build a LiquidBlock from a database row.
        """
        liquid_type = row[2]
        content_json = json.loads(row[8]) if row[8] else None
        content_obj = None
        if content_json:
            if isinstance(content_json, dict):
                # If the content is a single LiquidBlock
                content_obj = CatalogEntry.from_json_dict(content_json)
            elif isinstance(content_json, list):
                # or if its a list of blocks
                content_obj = []
                for entry in content_json:
                    content_obj.append(CatalogEntry.from_json_dict(entry))

        plan_json = json.loads(row[9]) if row[9] else None
        break_info = json.loads(row[7]) if row[7] else None

        start_time = datetime.fromisoformat(row[3])
        end_time = datetime.fromisoformat(row[4])
        args = (
            content_obj,
            start_time,
            end_time,
            row[6],  # title
            row[5],  # break_strategy
            break_info,
        )
        block = LiquidIO._block_factory(liquid_type, args)
        plans = []
        for p in plan_json:
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
