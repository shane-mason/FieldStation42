from enum import Enum
import time
import datetime
import json
import multiprocessing
import signal
import sys
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)

from python_mpv_jsonipc import MPV

from confs.fieldStation42_conf import main_conf, index_by_channel
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2
#from fs42.guide_channel import guide_channel_runner, GuideCommands
from fs42.guide_tk import guide_channel_runner, GuideCommands


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

class ReceptionStatus:

    def __init__(self, chaos=0, thresh=0.01):
        self.chaos = chaos
        self.thresh = thresh

    def is_perfect(self):
        return self.chaos == 0.0

    def is_degraded(self):
        return self.chaos >  self.thresh

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

class PlayerOutcome:
    def __init__(self, status=PlayStatus.SUCCESS, payload=None):
        self.status = status
        self.payload = payload

class FieldPlayer:

    def __init__(self, runtime_path, mpv=None):
        self._l = logging.getLogger("FieldPlayer")
        if not mpv:
            self._l.info("Starting MPV instance")
            #command on client: mpv --input-ipc-server=/tmp/mpvsocket --idle --force-window
            self.mpv = MPV(start_mpv=True, ipc_socket="/tmp/mpvsocket", input_default_bindings=False, fs=True, idle=True, force_window=True)
        self.runtime_path = runtime_path
        #self.playlist = self.read_json(runtime_filepath)
        self.index = 0

    def shutdown(self):
        self.mpv.terminate()

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
                return PlayerOutcome(PlayStatus.EXITED, e)

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
                    #only on first index we process, so toggle it off
                    offet_in_index = 0

                if seek_dur:
                    self.mpv.seek(seek_dur)
                    self._l.info(f"Seeking for: {seek_dur}")

                if wait_dur:
                    self._l.info(f"Monitoring for: {wait_dur}")


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





reception = ReceptionStatus()


def main_loop():
    degrade_amount = 0.02
    improve_amount = .1
    logger = logging.getLogger("MainLoop")
    logger.info("Starting main loop")

    channel_socket = main_conf['channel_socket']
    #go ahead and clear the channel socket (or create if it doesn't exist)
    with open(channel_socket, 'w'):
        pass

    channel_index = 0
    if not len(main_conf["stations"]):
        logger.error("Could not find any station runtimes - do you have your channels configured?")
        logger.error("Check to make sure you have valid json configurations in the confs dir")
        logger.error("The confs/examples folder contains working examples that you can build off of - just move one into confs/")
        return

    player = FieldPlayer(main_conf["stations"][channel_index])
    reception.degrade(1)
    player.update_filters()


    def sigint_handler(sig, frame):

        logger.critical("Recieved sig-int signal, attempting to exit gracefully...")
        player.shutdown()
        logger.critical("Shutdown is complete - exiting application")
        exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    channel_conf = main_conf['stations'][channel_index]
    while True:
        logger.info(f"Playing station: {channel_conf['network_name']}" )
        outcome = None

        # is this the guide channel?
        if  channel_conf["network_type"] == "guide":
            logger.info("Starting the guide channel")
            outcome = player.show_guide(channel_conf)
        else:
            now = datetime.datetime.now()
            week_day = DAYS[now.weekday()]
            hour = now.hour
            skip = now.minute * MIN_1 + now.second
            #skip = 60 * 59
            logger.info(f"Starting station {channel_conf['network_name']} at: {week_day} {hour} skipping={skip} ")
            outcome = player.play_slot(week_day, hour, skip, runtime_path=channel_conf["runtime_dir"])


        if outcome.status == PlayStatus.CHANNEL_CHANGE:
            tune_up = True
            #get the json payload
            if outcome.payload:
                try:
                    as_obj = json.loads(outcome.payload)
                    if "command" in as_obj and as_obj["command"] == "direct":
                        if "channel" in as_obj:
                            logger.info(f"Got direct tune command for channel {as_obj['channel']}")
                            new_index = index_by_channel(as_obj['channel'])
                            if not new_index:
                                logger.error(f"Got direct tune command but could not find station with channel {as_obj['channel']}")
                            else:
                                channel_index = new_index
                                tune_up = False
                        else:
                            logger.critical("Got direct tune command, but no channel specified")
                except Exception as e:
                    logger.exception(e)
                    logger.warning("Got payload on channel change, but JSON convert failed")


            if tune_up:
                logger.info("Starting channel change")
                channel_index+=1
                if channel_index>=len(main_conf["stations"]):
                    channel_index = 0
                
            channel_conf = main_conf["stations"][channel_index]

            #add noise to current channel
            while not reception.is_fully_degraded():
                reception.degrade(degrade_amount)
                player.update_filters()
                time.sleep(.05)

            #reception.improve(1)
            player.play_file("runtime/static.mp4")
            while not reception.is_perfect():
                reception.improve(improve_amount)
                player.update_filters()
                time.sleep(.05)
            time.sleep(1)
            while not reception.is_fully_degraded():
                reception.degrade(degrade_amount)
                player.update_filters()
                time.sleep(.05)

        elif outcome.status == PlayStatus.EXITED:
            logger.critical("Player exited - resting for 1 second and trying again")
            time.sleep(1)



if __name__ == "__main__":
    main_loop()
