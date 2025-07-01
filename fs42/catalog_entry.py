import os
import json

from fs42 import schedule_hint

class MatchingContentNotFound(Exception):
    pass


class NoFillerContentFound(Exception):
    pass


class CatalogEntry:
    # CatalogEntry(row[2], row[3], float(row[4]), json.loads(row[6]) if row[6] else [])
    def __init__(self, path, duration, tag, hints=[], count=0):
        self.path = path
        # get the show name from the path
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.duration = duration
        self.tag = tag
        self.count = count
        self.hints = hints

    def __str__(self):
        hints = list(map(str, self.hints))
        return f"{self.title:<20.20} | {self.tag:<10.10} | {self.duration:<8.1f} | {hints} | {self.path}"
    
    @staticmethod
    def from_db_row(row):

        (path, title, duration, tag, count, hints_str) = row


        entry = CatalogEntry(path, duration, tag, None)
        entry.count = count


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
                    if isinstance(hint, dict) and 'type' in hint:

                        if hint['type'] == 'day_part':
                            hints.append(schedule_hint.DayPartHint(hint['part']))
                        elif hint['type'] == 'bump':
                            hints.append(schedule_hint.BumpHint(hint['where']))
                        elif hint['type'] == 'range':
                            hints.append(schedule_hint.RangeHint(hint["range_string"]))
                        elif hint['type'] == 'quarter':
                            hints.append(schedule_hint.QuarterHint(hint["range_string"]))
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
