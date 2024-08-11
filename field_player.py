from python_mpv_jsonipc import MPV
import time
import datetime
import json
from timings import *

# You can also observe and wait for properties.
#@mpv.property_observer("eof-reached")
#def handle_eof(name, value):
#    print("time_remaining")
#    print(name)
#    print(value)

#mpv = MPV(start_mpv=False, ipc_socket="/tmp/mpvsocket")

#mpv.play("test1.mp4")
#mpv.wait_for_property("duration")
#print("Duration changed")
#mpv.seek(1234)
#time.sleep(10)
#mpv.play("test0.mp4")
#time.sleep(10)
#mpv.play("test1.mp4")
#mpv.wait_for_property("duration")
#mpv.seek("300")


class FieldPlayer:

    def __init__(self, runtime_path, mpv=None):
        if not mpv:
            #command on client: mpv --input-ipc-server=/tmp/mpvsocket --idle --force-window
            self.mpv = MPV(start_mpv=True, ipc_socket="/tmp/mpvsocket", input_default_bindings=False)
        self.runtime_path = runtime_path
        #self.playlist = self.read_json(runtime_filepath)
        self.index = 0

    def play_image(self, duration):
        pass

    def play_slot(self, the_day, the_hour, offset=0):
        fpath = f"{self.runtime_path}/{the_day}_{the_hour}.json";
        print("Playing: " + fpath)
        self.playlist = self.read_json(fpath)
        self.start_playing(offset)

    def read_json(self, file_path):
        playlist = None
        with open(file_path, "r") as f:
            as_str = f.read()
            playlist = json.loads(as_str)
        return playlist


    def start_playing(self, block_offset=0):
        offset_in_index = 0
        if block_offset:
            print("Getting block offset")
            (index, offset) = self._find_index_at_offset(block_offset)
            print(f"index,offset = {index},{offset}")
            self.index = index
            offset_in_index = offset
        self._play_from_index(offset_in_index)

    def _find_index_at_offset(self, offset):
        abs_start = 0
        abs_end = 0
        index = 0
        for _entry in self.playlist:
            abs_start = abs_end
            abs_end = abs_start + _entry['duration']
            if offset > abs_start and offset <= abs_end:
                d2 = offset - abs_start
                return(index, d2)
            index += 1

    def _play_from_index(self, offet_in_index=0):
        if self.index < len(self.playlist):
            #iterate over the slice from index to end
            for entry in self.playlist[self.index:]:
                print("Playing: ", entry)
                self.mpv.play(entry["path"])
                self.mpv.wait_for_property("duration")
                sleep_dur = entry['duration']
                seek_dur = 0

                #do any initial seek
                if entry['start'] != 0:
                    seek_dur += entry['start']

                if offet_in_index:
                    seek_dur += offet_in_index
                    sleep_dur -= offet_in_index
                    #only on first index we process, so toggle it off
                    offet_in_index = 0

                if seek_dur:
                    self.mpv.seek(seek_dur)
                    print(f"seeking for: {seek_dur}")

                if sleep_dur:
                    print(f"sleeping for: {sleep_dur}")
                    time.sleep(sleep_dur-.1)

            print("Done playing block")
            return True
        else:
            return False

if __name__ == "__main__":
    player = FieldPlayer("runtime/abc")
    while True:
        now = datetime.datetime.now()
        #how far are we from the next hour?
        if now.minute == 59:
            #then just play some filler until next hour +1 second
            to_fill = (MIN_1-now.second)+1
            print(f"Filling time between blocks: {to_fill}")
            time.sleep(to_fill)
            now = datetime.datetime.now()

        week_day = DAYS[now.weekday()]
        hour = now.hour
        skip = now.minute * MIN_1 + now.second

        player.play_slot(week_day, hour, skip)
