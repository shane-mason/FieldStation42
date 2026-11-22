import datetime


class FileRepoEntry:
    def __init__(self, db_row=None):
        if not db_row:
            self.path: str = None
            self.duration: float = 0.0
            self.size: int = 0
            self.first_added: datetime.datetime = None
            self.last_mod: datetime.datetime = None
            self.last_checked: datetime.datetime = None
            self.last_updates: datetime.datetime = None
            self.meta = ""
            self.media_type = "video"
        else:
            self.from_db_row(db_row)

    def __str__(self):
        return f"Path:{self.path}, Dur:{self.duration}, Sz:{self.size}, Mod:{self.last_mod}"

    def __eq__(self, value):
        return self.to_stat_check() == value.to_stat_check()

    def from_db_row(self, row):
        # Handle both old (8 columns) and new (9 columns with media_type) schemas
        if len(row) == 9:
            (
                self.path,
                self.duration,
                self.size,
                self.first_added,
                self.last_mod,
                self.last_checked,
                self.last_updates,
                self.meta,
                self.media_type,
            ) = row
        else:  # Old schema with 8 columns
            (
                self.path,
                self.duration,
                self.size,
                self.first_added,
                self.last_mod,
                self.last_checked,
                self.last_updates,
                self.meta,
            ) = row
            self.media_type = "video"  # Default for backward compatibility

    def to_db_row(self):
        return (
            self.path,
            self.duration,
            self.size,
            self.first_added,
            self.last_mod,
            self.last_checked,
            self.last_updates,
            self.meta,
        )

    def to_stat_check(self):
        return (self.path, self.size, self.last_mod)
