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
            self.last_upates: datetime.datetime = None
            self.meta = ""
        else:
            self.from_db_row(db_row)

    def __str__(self):
        return f"Path:{self.path}, Dur:{self.duration}, Sz:{self.size}, Mod:{self.last_mod}"

    def __eq__(self, value):
        return self.to_stat_check() == value.to_stat_check()

    def from_db_row(self, row):
        (
            self.path,
            self.duration,
            self.size,
            self.first_added,
            self.last_mod,
            self.last_checked,
            self.last_upates,
            self.meta,
        ) = row

    def to_db_row(self):
        return (
            self.path,
            self.duration,
            self.size,
            self.first_added,
            self.last_mod,
            self.last_checked,
            self.last_upates,
            self.meta,
        )

    def to_stat_check(self):
        return (self.path, self.size, self.last_mod)
