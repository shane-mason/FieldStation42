import math

class SequenceEntry:
    def __init__(self, fpath):
        self.fpath = str(fpath)

    def __str__(self):
        return f"SequenceEntry(fpath={self.fpath})"

class NamedSequence:
    def __init__(self, station_name: str, sequence_name: str, tag_path: str, start_perc: float, end_perc: float, current_index: int):
        self.station_name = station_name
        self.sequence_name = sequence_name
        self.tag_path = tag_path
        self.start_perc = start_perc
        self.end_perc = end_perc
        self.current_index = current_index
        self.episodes = []  
        self.__defaults()

    def __str__(self):
        return f"NamedSequence(station={self.station_name}, sequence={self.sequence_name}, tag={self.tag_path}, start={self.start_perc}, end={self.end_perc}, index={self.current_index})"

    def populate(self, file_list):
        self.episodes = []  # Reset the episodes list
        for file in file_list:
            entry = SequenceEntry(file)
            self.episodes.append(entry)

        # explicitely sort them by file path for alpha-numeric ordering:
        self.episodes = sorted(self.episodes, key=lambda entry: entry.fpath)
        self.__defaults()
        self.current_index = self.start_index

    def get_series_length(self):
        return len(self._episodes)

    def __defaults(self):
        # handle previous catalog versions
        self.start_index = math.floor(self.start_perc * (len(self.episodes)))
        self.end_index = math.floor(self.end_perc * (len(self.episodes)))

