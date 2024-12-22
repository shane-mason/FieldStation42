from enum import Enum
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)
import multiprocessing
import time
import datetime
import json

from python_mpv_jsonipc import MPV

from confs.fieldStation42_conf import main_conf
from fs42.guide_tk import guide_channel_runner, GuideCommands
from fs42.reception import ReceptionStatus

def check_channel_socket():
    channel_socket = main_conf['channel_socket']
    r_sock = open(channel_socket, "r")
    contents = r_sock.read()
    r_sock.close()
    if len(contents):
        with open(channel_socket, 'w'):
            pass
        return PlayerOutcome(PlayStatus.CHANNEL_CHANGE, contents)
    return None

class PlayStatus(Enum):
    FAILED = 1
    EXITED = 2
    SUCCESS = 3
    CHANNEL_CHANGE =4

class PlayerOutcome:
    def __init__(self, status=PlayStatus.SUCCESS, payload=None):
        self.status = status
        self.payload = payload

class StationPlayer:

    def __init__(self, runtime_path, mpv=None):
        self._l = logging.getLogger("FieldPlayer")
        if not mpv:
            self._l.info("Starting MPV instance")
            #command on client: mpv --input-ipc-server=/tmp/mpvsocket --idle --force-window
            self.mpv = MPV(start_mpv=True, ipc_socket="/tmp/mpvsocket", input_default_bindings=False, fs=True, idle=True, force_window=True)
        self.runtime_path = runtime_path
        #self.playlist = self.read_json(runtime_filepath)
        self.index = 0
        self.reception = ReceptionStatus()

    def show_text(self, text, duration=4):
        self.mpv.command("show-text", text, duration)

    def shutdown(self):
        self.mpv.terminate()

    def update_filters(self):
        self.mpv.vf = self.reception.filter()

    def update_reception(self):
        if not self.reception.is_perfect():
            self.reception.improve()
            #did that get us below threshhold?
            if self.reception.is_perfect():
                self.mpv.vf = ""
            else:
                self.mpv.vf = self.reception.filter()

    def play_file(self, file_path):
        self.mpv.play(file_path)
        self.mpv.wait_for_property("duration")
        return

    def play_image(self, duration):
        pass

    def show_guide(self, guide_config):
        #create the pipe to communicate with the guide channel
        queue = multiprocessing.Queue()
        guide_process = multiprocessing.Process(target=guide_channel_runner, args=( guide_config, queue,))
        guide_process.start()

        self.mpv.stop()

        keep_going = True
        while keep_going:
            time.sleep(.05)
            response = check_channel_socket()
            if response:
                self._l.info("Sending the guide channel shutdown command")
                queue.put(GuideCommands.hide_window)
                guide_process.join()
                return response

        return PlayerOutcome(PlayStatus.SUCCESS)

    def play_slot(self, the_day, the_hour, offset=0, runtime_path=None):

        if runtime_path:
            self.runtime_path = runtime_path
        fpath = f"{self.runtime_path}/{the_day}_{the_hour}.json";
        self._l.info(f"Loading slot playlist on path: {fpath}")
        self.playlist = self.read_json(fpath)
        self._l.info(f"Slot playlist: {self.playlist}")
        return self.start_playing(offset)

    def read_json(self, file_path):
        playlist = None
        with open(file_path, "r") as f:
            as_str = f.read()
            playlist = json.loads(as_str)
        return playlist

    def start_playing(self, block_offset=0):
        self._l.info(f"Starting to play offset in block {block_offset}")
        offset_in_index = 0
        if block_offset:
            try:
                (index, offset) = self._find_index_at_offset(block_offset)
            except TypeError as e:
                self._l.critical("Error getting index and offset - exiting playback")
                return PlayerOutcome(PlayStatus.FAILED, e)

            self._l.info(f"Calculated offsets index|offset = {index}|{offset}")
            self.index = index
            offset_in_index = offset
        else:
            self.index = 0
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
                self._l.info(f"Playing entry {entry}")
                
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
                    #we process only on first index, so toggle it off
                    offet_in_index = 0

                if seek_dur:
                    self.mpv.seek(seek_dur)
                    self._l.info(f"Seeking for: {seek_dur}")

                if wait_dur:
                    self._l.info(f"Monitoring for: {wait_dur}")
                    #self.show_text(f"Playing entry {entry}", 4)
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
                            response = check_channel_socket()
                            if response:
                                return response

            self._l.info("Done playing block")
            return PlayerOutcome(PlayStatus.SUCCESS)
        else:
            return PlayerOutcome(PlayStatus.FAILED, "Failure getting index...")




