import os
import json

from fs42 import schedule_hint


class MatchingContentNotFound(Exception):
    pass


class NoFillerContentFound(Exception):
    pass


class CatalogEntry:
    # CatalogEntry(row[2], row[3], float(row[4]), json.loads(row[6]) if row[6] else [])
    def __init__(self, path, duration, tag, hints=[], count=0, content_type="feature"):
        self.path = path
        self.realpath = None
        # get the show name from the path
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.duration = duration
        self.tag = tag
        self.count = count
        self.hints = hints
        self.content_type = content_type
        self.station = None
        self.dbid = None
        self.created_at = None
        self.updated_at = None

    def __str__(self):
        hints = list(map(str, self.hints))
        return f"{self.title:<20.20} | {self.tag:<10.10} | {self.duration:<8.1f} | {hints} | {self.path}"

    def toJSON(self):
        # Convert the entry to a JSON serializable dictionary
        return {
            "dbid": self.dbid,
            "path": self.path,
            "title": self.title,
            "duration": self.duration,
            "tag": self.tag,
            "count": self.count,
            "content_type": self.content_type,
            "hints": [hint.toJSON() for hint in self.hints],  # Convert each hint to JSON
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def from_json_dict(json_data):
        # Create an entry from a JSON serializable dictionary
        tup = (
            json_data["dbid"],
            json_data["station"],
            json_data["path"],
            json_data["title"],
            json_data["duration"],
            json_data["tag"],
            json_data["count"],
            json_data["hints"],
            json_data.get("created_at", None),
            json_data.get("updated_at", None),
            json_data.get("realpath", None),
            json_data.get("content_type", "feature"),
        )
        return CatalogEntry.from_db_row(tup)

    @staticmethod
    def from_db_row(row):

        if len(row) == 12:  # New schema with realpath and content_type
            (dbid, station, path, title, duration, tag, count, hints_str, created, updated, realpath, content_type) = row
        elif len(row) == 11:  # Schema with realpath but no content_type
            (dbid, station, path, title, duration, tag, count, hints_str, created, updated, realpath) = row
            content_type = "feature"  # Default for backward compatibility
        else:  # Old schema without realpath
            (dbid, station, path, title, duration, tag, count, hints_str, created, updated) = row
            realpath = None
            content_type = "feature"  # Default for backward compatibility


        entry = CatalogEntry(path, duration, tag, None, count, content_type)
        entry.realpath = realpath
        entry.count = count
        entry.dbid = dbid
        entry.station = station
        entry.created_at = created
        entry.updated_at = updated

        hints = []
        # Load hints from JSON
        if hints_str:
            try:
                # Parse the JSON string back to list
                loaded_hints = json.loads(hints_str)

                if not isinstance(loaded_hints, list):
                    loaded_hints = []

                for hint_str in loaded_hints:
                    hint = json.loads(hint_str)
                    # Convert each hint JSON back to its object
                    if isinstance(hint, dict) and "type" in hint:
                        if hint["type"] == "day_part":
                            hints.append(schedule_hint.DayPartHint(hint["part"]))
                        elif hint["type"] == "bump":
                            hints.append(schedule_hint.BumpHint(hint["where"]))
                        elif hint["type"] == "range":
                            hints.append(schedule_hint.RangeHint(hint["range_string"]))
                        elif hint["type"] == "quarter":
                            hints.append(schedule_hint.QuarterHint(hint["quarter"]))
                        elif hint["type"] == "month":
                            hints.append(schedule_hint.MonthHint(hint["month"]))
                        else:
                            print(f"Warning: Unknown hint type {hint['type']}. Skipping.")
                    else:
                        print(f"Warning: Invalid hint format {hint}. Skipping.")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Failed to decode hints from string '{hints_str}'. Using empty hints list.")
                print(f"Error: {e}")
                hints = []

        entry.hints = hints
        return entry
