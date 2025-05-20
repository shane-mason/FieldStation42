from datetime import datetime
from fs42.media_processor import MediaProcessor

class SequenceEntry:

    def __init__(self, fpath, scheduled=[], last_played=None):
        self.fpath = str(fpath)
        self.next_scheduled = scheduled
        self.last_played = last_played

class SeriesIndex:

    def __init__(self, tag_path ):
        self.tag_path = tag_path
        self._episodes = []
        self._index = -1

    @staticmethod
    def make_key(series_name, sequence_name):
        return f"{series_name}-{sequence_name}"

    def populate(self, file_list):
    
        for file in file_list:
            entry = SequenceEntry(file)
            self._episodes.append(entry)
        
        #explicitely sort them by file path for alpha-numeric ordering:
        self._episodes = sorted(self._episodes, key=lambda entry: entry.fpath)
        

    def get_series_length(self):
        return len(self._episodes)
    
    def get_next(self):
        if self._index < 0 or self._index >= len(self._episodes):
            self._index = 0
        else:
            self._index+=1
            self._index = 0 if self._index >= len(self._episodes) else self._index 
        
        return self._episodes[self._index].fpath
    
    def get_current(self):
        return self._episodes[self._index].fpath

    def schedule_episode(self, fpath):
        pass

    def _by_fpath(self, fpath):
        for episode in self._episodes:
            if episode.fpath == fpath:
                return fpath
            