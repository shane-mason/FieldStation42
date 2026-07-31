import os
import json
import sqlite3
import logging
from fs42.database import connect

_logger = logging.getLogger("MetadataIO")


class MetadataIO:

    @staticmethod
    def _default_db_path():
        from fs42.station_manager import StationManager
        return StationManager().server_conf["db_path"]

    @staticmethod
    def normalize(meta):
        if not isinstance(meta, dict):
            return meta

        # Legacy audio rows stored the year under `date` and carried no type
        # discriminator. Bring them up to the normalized shape on read.
        needs_year = "date" in meta and "year" not in meta
        needs_type = "type" not in meta
        if needs_year or needs_type:
            meta = dict(meta)
            if needs_year:
                meta["year"] = meta.pop("date")
            if needs_type:
                meta["type"] = "music"
        return meta

    @staticmethod
    def read(file_path, db_path=None):
        if db_path is None:
            try:
                db_path = MetadataIO._default_db_path()
            except Exception as e:
                _logger.warning(f"Could not resolve db_path for metadata read: {e}")
                return None

        try:
            real_path = os.path.realpath(os.path.abspath(file_path))
            with connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT meta FROM file_meta WHERE path = ?", (real_path,))
                row = cursor.fetchone()
                cursor.close()

            if row and row[0]:
                return MetadataIO.normalize(json.loads(row[0]))
        except Exception as e:
            _logger.warning(f"Could not read metadata for {file_path}: {e}")

        return None
