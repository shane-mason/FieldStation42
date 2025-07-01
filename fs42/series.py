import math

class SequenceEntry:
    def __init__(self, fpath):
        self.fpath = str(fpath)

    def __str__(self):
        return f"SequenceEntry(fpath={self.fpath})"

class SeriesIndex:
    def __init__(self, tag_path, start_point=0, end_point=1):
        self.tag_path = tag_path
        self._episodes: list[SequenceEntry] = []
        self._index = -1
        if start_point < 0 or start_point > 1 or start_point > end_point:
            raise ValueError(
                f"Sequence start point for {tag_path} must be more than 0, less than 1 and less than sequence end. Check your configuration."
            )
        if end_point < 0 or end_point > 1:
            raise ValueError(
                f"Sequence end point for {tag_path} must be greater than zero and less than 1. Check your configuration."
            )
        self._start_perc = start_point
        self._end_perc = end_point
        self.__defaults()

    def __str__(self):
        a =  f"SeriesIndex({self.tag_path}, {self._start_perc}, {self._end_perc}) self._episodes={len(self._episodes)}, index={self._index})\n"
        for episode in self._episodes:
            a += f"  {episode}\n"
        return a

    @staticmethod
    def make_key(series_name, sequence_name):
        return f"{series_name}-{sequence_name}"

    def populate(self, file_list):
        for file in file_list:
            entry = SequenceEntry(file)
            self._episodes.append(entry)

        # explicitely sort them by file path for alpha-numeric ordering:
        self._episodes = sorted(self._episodes, key=lambda entry: entry.fpath)
        self.__defaults()
        self._index = self._start_index

    def get_series_length(self):
        return len(self._episodes)

    def __defaults(self):
        if not hasattr(self, "_start_perc"):
            self._start_perc = 0
        if not hasattr(self, "_end_perc"):
            self._end_perc = 1

        # handle previous catalog versions
        self._start_index = math.floor(self._start_perc * (len(self._episodes)))
        self._end_index = math.floor(self._end_perc * (len(self._episodes)))

    def get_next(self):
        self.__defaults()
        to_return = None
        if self._index < 0 or self._index >= self._end_index:
            self._index = self._start_index
            to_return = self._episodes[self._index].fpath
        else:
            to_return = self._episodes[self._index].fpath
            self._index += 1
            if self._index >= self._end_index:
                self._index = self._start_index

        return to_return

    def get_current(self):
        return self._episodes[self._index].fpath

    def reset_by_fpath(self, fpath):
        for i in range(len(self._episodes)):
            if self._episodes[i].fpath == fpath:
                self._index = i
                break

        # now, we want to go one episode earlier, so that this is the next episode
        self._index -= 1
        # wrap back to the end if we went negative
        self._index = (len(self._episodes) - 1) if self._index < 0 else self._index

    def _by_fpath(self, fpath):
        for episode in self._episodes:
            if episode.fpath == fpath:
                return fpath
