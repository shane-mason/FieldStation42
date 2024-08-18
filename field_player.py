from python_mpv_jsonipc import MPV
from enum import Enum
import time
import datetime
import json
from timings import *

channel_socket = "runtime/channel.socket"

class ReceptionStatus:

    def __init__(self, chaos=0, thresh=0.01):
        self.chaos = chaos
        self.thresh = thresh

    def is_perfect(self):
        return self.chaos == 0.0

    def is_degraded(self):
        return self.chaos > threshhold

    def is_fully_degraded(self):
        return self.chaos == 1.0


    def degrade(self, amount=.02):
        self.chaos += amount
        if self.chaos > 1.0:
            self.chaos = 1.0

    def improve(self, amount=.02):
        self.chaos-=amount
        if self.chaos < self.thresh:
            self.chaos = 0.0


    def filter(self):
        if self.chaos > self.thresh:
            #between 0 and 100
            noise = self.chaos * 100
            #between 0 and .5
            v_scroll = self.chaos * .5
            return f"lavfi=[noise=alls={noise}:allf=t+u, scroll=h=0:v={v_scroll}]"
        else:
            return ""

class PlayStatus(Enum):
    FAILED = 1
    EXITED = 2
    SUCCESS = 3
    CHANNEL_CHANGE =4

class FieldPlayer:

    def __init__(self, runtime_path, mpv=None):
        if not mpv:
            #command on client: mpv --input-ipc-server=/tmp/mpvsocket --idle --force-window
            self.mpv = MPV(start_mpv=True, ipc_socket="/tmp/mpvsocket", input_default_bindings=False)
        self.runtime_path = runtime_path
        #self.playlist = self.read_json(runtime_filepath)
        self.index = 0

    def update_filters(self):
        self.mpv.vf = reception.filter()

    def update_reception(self):
        if not reception.is_perfect():
            reception.improve()
            #did that get us below threshhold?
            if reception.is_perfect():
                self.mpv.vf = ""
            else:
                self.mpv.vf = reception.filter()

    def play_file(self, file_path):
        self.mpv.play(file_path)
        self.mpv.wait_for_property("duration")
        return

    def play_image(self, duration):
        pass

    def play_slot(self, the_day, the_hour, offset=0, runtime_path=None):
        if runtime_path:
            self.runtime_path = runtime_path
        fpath = f"{self.runtime_path}/{the_day}_{the_hour}.json";
        print("Playing: " + fpath)
        self.playlist = self.read_json(fpath)
        return self.start_playing(offset)

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
        return self._play_from_index(offset_in_index)

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

    #returns true if play is interrupted
    def _play_from_index(self, offet_in_index=0):

        if self.index < len(self.playlist):
            #iterate over the slice from index to end
            for entry in self.playlist[self.index:]:
                print("Playing: ", entry)
                self.mpv.play(entry["path"])
                self.mpv.wait_for_property("duration")
                wait_dur = entry['duration']
                seek_dur = 0

                #do any initial seek
                if entry['start'] != 0:
                    seek_dur += entry['start']

                if offet_in_index:
                    seek_dur += offet_in_index
                    wait_dur -= offet_in_index
                    #only on first index we process, so toggle it off
                    offet_in_index = 0

                if seek_dur:
                    self.mpv.seek(seek_dur)
                    print(f"seeking for: {seek_dur}")

                if wait_dur:
                    print(f"monitoring for: {wait_dur}")


                    #this is our main event loop
                    keep_waiting = True
                    stop_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_dur)
                    while keep_waiting:

                        self.update_reception()
                        now = datetime.datetime.now()

                        if now >= stop_time:
                            keep_waiting = False
                        else:
                            #debounce time
                            time.sleep(.05)
                            r_sock = open(channel_socket, "r")
                            contents = r_sock.read()
                            r_sock.close()
                            if len(contents):
                                print("Contents updated - resetting socket file")
                                with open(channel_socket, 'w'):
                                    pass

                                return PlayStatus.CHANNEL_CHANGE

            print("Done playing block")
            return PlayStatus.SUCCESS
        else:
            return PlayStatus.FAILED

reception = ReceptionStatus()


def main_loop():

    #get the channels and runtimes
    from confs.fieldStation42_conf import main_conf
    station_runtimes = []
    for c in main_conf["stations"]:
        #go through each station config and get its runtime
        station_runtimes.append(c['runtime_dir'])

    global channel_socket
    channel_socket = main_conf['channel_socket']

    #go ahead and clear the channel socket (or create if it doesn't exist)
    with open(channel_socket, 'w'):
        pass

    station_runtimes = ["runtime/nbc", "runtime/abc", "runtime/pbs"]
    channel = 0
    player = FieldPlayer(station_runtimes[channel])
    reception.degrade(1)
    player.update_filters()

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

        outcome = player.play_slot(week_day, hour, skip, runtime_path=station_runtimes[channel])

        if outcome == PlayStatus.CHANNEL_CHANGE:
            channel+=1
            if channel>=len(station_runtimes):
                channel = 0

            #add noise to current channel
            while not reception.is_fully_degraded():
                reception.degrade()
                player.update_filters()
                time.sleep(.05)

            #reception.improve(1)
            player.play_file("runtime/static.mp4")
            while not reception.is_perfect():
                reception.improve(.1)
                player.update_filters()
                time.sleep(.1)
            time.sleep(1)
            while not reception.is_fully_degraded():
                reception.degrade(.1)
                player.update_filters()
                time.sleep(.1)


if __name__ == "__main__":
    main_loop()
