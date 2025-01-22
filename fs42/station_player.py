from enum import Enum
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)
import multiprocessing
import time
import datetime
import json

from python_mpv_jsonipc import MPV

from fs42.guide_tk import guide_channel_runner, GuideCommands
from fs42.reception import ReceptionStatus
from fs42.liquid_manager import LiquidManager, PlayPoint
from fs42.station_manager import StationManager

def check_channel_socket():
    channel_socket = StationManager().server_conf['channel_socket']
    r_sock = open(channel_socket, "r")
    contents = r_sock.read()
    r_sock.close()
    if len(contents):
        with open(channel_socket, 'w'):
            pass
        return PlayerOutcome(PlayStatus.CHANNEL_CHANGE, contents)
    return None

def update_status_socket(status, network_name, channel):
    status_obj = {
        "status": status,
        "network_name": network_name,
        "channel_number": channel,
        "timestamp": datetime.datetime.now().isoformat()
    }
    status_socket = StationManager().server_conf['status_socket']
    as_str = json.dumps(status_obj)
    with open(status_socket, "w") as fp:
        fp.write(as_str)

        

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

    def play_slot(self , network_name, when):
        liquid = LiquidManager()
        play_point = liquid.get_play_point(network_name, when)
        if play_point == None:
            return PlayerOutcome(PlayStatus.FAILED)
        return self._play_from_point(play_point)

    #returns true if play is interrupted
    def _play_from_point(self, play_point:PlayPoint):

        if len(play_point.plan):

            initial_skip = play_point.offset
            
            #iterate over the slice from index to end
            for entry in play_point.plan[play_point.index:]:
                self._l.info(f"Playing entry {entry}")
                self._l.info(f"Initial Skip: {initial_skip}")
                self.mpv.play(entry.path)
                self.mpv.wait_for_property("duration")
                
                total_skip = entry.skip + initial_skip
                self.mpv.seek(total_skip)
                self._l.info(f"Seeking for: {total_skip}")
                

                if entry.duration:
                    self._l.info(f"Monitoring for: {entry.duration-initial_skip}")
            
                    #this is our main event loop
                    keep_waiting = True
                    stop_time = datetime.datetime.now() + datetime.timedelta(seconds=entry.duration-initial_skip)
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
                else:
                    raise(PlayerOutcome(PlayStatus.FAILED))
                
                initial_skip = 0

            self._l.info("Done playing block")
            return PlayerOutcome(PlayStatus.SUCCESS)
        else:
            return PlayerOutcome(PlayStatus.FAILED, "Failure getting index...")




