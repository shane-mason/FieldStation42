import math
import random
import logging

class SequenceEntry:
    def __init__(self, fpath):
        self.fpath = str(fpath)

    def __str__(self):
        return f"SequenceEntry(fpath={self.fpath})"


class NamedSequence:
    def __init__(
        self,
        station_name: str,
        sequence_name: str,
        tag_path: str,
        start_perc: float,
        end_perc: float,
        current_index: int,
        file_list: list[str],
        initialized: bool = False
    ):
        self._l = logging.getLogger(f"{self.__class__.__name__}")
        self.station_name = station_name
        self.sequence_name = sequence_name
        self.tag_path = tag_path
        self.start_perc = start_perc
        self.end_perc = end_perc
        self.current_index = current_index
        self.initialized = initialized
        self.episodes = []  # Initialize episodes as an empty list
        self.start_index = 0
        self.end_index = 0
        self.populate(file_list)  # Populate episodes with the provided file list



    def __str__(self):
        return f"NamedSequence(station={self.station_name}, sequence={self.sequence_name}, tag={self.tag_path}, start={self.start_perc}, end={self.end_perc}, index={self.current_index})"

    def populate(self, file_list):
        self.episodes = []  # Reset the episodes list
        for file in file_list:
            entry = SequenceEntry(file)
            self.episodes.append(entry)

        # explicitely sort them by file path for alpha-numeric ordering:
        self.episodes = sorted(self.episodes, key=lambda entry: entry.fpath)

        # Clamp to the episode count - end_perc > 1 (misconfiguration) must not
        # push end_index past the last episode, or the completion check in
        # SequenceAPI.get_next_in_sequence can be skipped and cause an IndexError.
        self.end_index = min(
            math.floor(self.end_perc * (len(self.episodes))),
            len(self.episodes),
        )

        # start_index is derived from start_perc - recompute it on every load,
        # not just on first init, so loop-back / reset lands on the configured
        # start rather than 0. A negative start_perc means "start anywhere", so
        # the window opens at 0.
        if self.start_perc < 0:
            self.start_index = 0
        else:
            self.start_index = min(
                math.floor(self.start_perc * (len(self.episodes))),
                max(self.end_index - 1, 0),
            )

        if not self.initialized:
            try:
                if self.start_perc < 0:
                    self.current_index = random.randrange(self.start_index, self.end_index)
                else:
                    self.current_index = self.start_index
            except Exception as e:
                self._l.error("Error populating sequence - please check that you have the correct configuration")
                self._l.error("Current configuration for this sequence below:")
                self._l.error(str(self))
                if len(self.episodes) < 1:
                    self._l.error("The error is caused by not having any episodes in your sequence - check your tag path and sequence name")
                raise e
            self.initialized = True

    def get_series_length(self):
        return len(self._episodes)
