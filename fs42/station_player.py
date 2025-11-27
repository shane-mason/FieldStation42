from enum import Enum
import logging

import multiprocessing
import time
import datetime
import json
import os
import glob
import random

from python_mpv_jsonipc import MPV

from fs42.guide_tk import guide_channel_runner, GuideCommands
from fs42.autobump_agent import AutoBumpAgent

# Try to import web_render_runner, but handle gracefully if PySide6 isn't available
try:
    from fs42.webrender.web_render import web_render_runner
    WEB_RENDER_AVAILABLE = True
except ImportError:
    WEB_RENDER_AVAILABLE = False
    web_render_runner = None

from fs42.reception import (
    ReceptionStatus,
    HLScrambledVideoFilter,
    DiagonalScrambledVideoFilter,
    ColorInvertedScrambledVideoFilter,
    ChunkyScrambledVideoFilter,
)
from fs42.liquid_manager import LiquidManager, PlayPoint, ScheduleNotFound, ScheduleQueryNotInBounds

from fs42.liquid_schedule import LiquidSchedule
from fs42.station_manager import StationManager
from fs42.slot_reader import SlotReader

logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO)


def update_status_socket(
    status, network_name, channel, title=None, timestamp="%Y-%m-%dT%H:%M:%S", duration=None, file_path=None, content_type=None
):
    status_obj = {
        "status": status,
        "network_name": network_name,
        "channel_number": channel,
        "timestamp": datetime.datetime.now().strftime(timestamp),
    }
    if title is not None:
        status_obj["title"] = title
    if duration is not None:
        status_obj["duration"] = duration
    if file_path is not None:
        status_obj["file_path"] = file_path
    if content_type is not None:
        status_obj["content_type"] = content_type
    status_socket = StationManager().server_conf["status_socket"]
    as_str = json.dumps(status_obj)
    with open(status_socket, "w") as fp:
        fp.write(as_str)


class PlayerState(Enum):
    FAILED = 1
    EXITED = 2
    SUCCESS = 3
    CHANNEL_CHANGE = 4
    EXIT_COMMAND = 5


class PlayerOutcome:
    def __init__(self, status=PlayerState.SUCCESS, payload=None):
        self.status = status
        self.payload = payload


class StationPlayer:
    scramble_effects = {
        "horizontal_line": "lavfi=[geq='if(mod(floor(Y/4),2),p(X,Y+20*sin(2*PI*X/50)),p(X,Y))']",
        "diagonal_lines": "lavfi=[geq='p(X+10*sin(2*PI*Y/30),Y)']",
        "static_overlay": "lavfi=[geq='if(gt(random(X+Y*W),0.85),128+127*random(X*Y),if(mod(floor(Y/4),2),p(X+20,Y),p(X,Y)))']",
        "pixel_block": "lavfi=[scale=160:120,scale=640:480:flags=neighbor,geq='if(gt(random(floor(X/40)*floor(Y/30)),0.7),128,p(X,Y))']",
        "color_inversion": "lavfi=[geq='if(mod(floor(Y/16),2),255-p(X,Y),p(X,Y))']",
        "severe_noise": "lavfi=[geq='if(gt(random(X*Y),0.7),random(255),p(X,Y))']",
        "wavy": "lavfi=[geq='p(X+15*sin(2*PI*Y/40),Y+10*cos(2*PI*X/60))']",
        "random_block": "lavfi=[geq='if(gt(random(floor(X/20)*floor(Y/20)),0.6),p(X+random(100)-20,Y+random(70)-20),p(X,Y))']",
        "chunky_scramble": "lavfi=[scale=320:240,split[base][aux];[aux]geq=r='p(X+floor((random(1000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':g='p(X+floor((random(2000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':b='p(X+floor((random(3000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)'[warped];[base][warped]overlay,scale=640:480]",
    }

    def __init__(self, station_config, input_check_fn, mpv=None):
        self._l = logging.getLogger("FieldPlayer")

        start_it = True

        if "start_mpv" in StationManager().server_conf:
            start_it = StationManager().server_conf["start_mpv"]

        if not mpv:
            self._l.info("Starting MPV instance")
            # command on client: mpv --input-ipc-server=/tmp/mpvsocket --idle --force-window 

            # if not running on trixie
            self.mpv = MPV(
                start_mpv=start_it,
                ipc_socket="/tmp/mpvsocket",
                input_default_bindings=False,
                fs=True,
                idle=True,
                force_window=True,
                script_opts="osc-idlescreen=no",
            )

        self.station_config = station_config
        # self.playlist = self.read_json(runtime_filepath)
        self.input_check_fn = input_check_fn
        self.index = 0
        self.reception = ReceptionStatus()
        self.current_playing_file_path = None
        self.skip_reception_check = False
        self.web_process = None
        self.web_queue = None
        self.scrambler = None

    def show_text(self, text, duration=4):
        self.mpv.command("show-text", text, duration)

    def shutdown(self):
        self.current_playing_file_path = None
        # Terminate any running web process
        if self.web_process and self.web_process.is_alive():
            self._l.info("Terminating web process")
            try:
                if self.web_queue:
                    self.web_queue.put("hide_window")
                self.web_process.join(timeout=2)
            except Exception:
                pass
            
            # Check if process is still alive and has valid _popen
            if self.web_process and hasattr(self.web_process, '_popen') and self.web_process._popen and self.web_process.is_alive():
                try:
                    self.web_process.terminate()
                    self.web_process.join(timeout=1)
                except Exception:
                    pass
                    
        self.web_process = None
        self.web_queue = None
        self.mpv.terminate()

    def update_filters(self):
        self.mpv.vf = self.reception.filter()

    def update_reception(self):
        if not self.reception.is_perfect():
            self.reception.improve()
            # did that get us below threshhold?
            if self.reception.is_perfect():
                self.mpv.vf = ""
            else:
                self.mpv.vf = self.reception.filter()

    def play_file(self, file_path, file_duration=None, current_time=None, is_stream=False, title="Unknown", content_type=None):
        try:
            if os.path.exists(file_path) or is_stream or AutoBumpAgent.is_autobump_url(file_path):
                self._l.debug(f"%%%Attempting to play {file_path}")
                self.current_playing_file_path = file_path

                if self.station_config:
                    self._l.debug("Got station config, updating status socket")
                    if "date_time_format" in StationManager().server_conf:
                        ts_format = StationManager().server_conf["date_time_format"]
                    else:
                        ts_format = "%Y-%m-%dT%H:%M:%S"
                    duration = (
                        f"{str(datetime.timedelta(seconds=int(current_time)))}/{str(datetime.timedelta(seconds=int(file_duration)))}"
                        if file_duration
                        else "n/a"
                    )
                    update_status_socket(
                        "playing",
                        self.station_config["network_name"],
                        self.station_config["channel_number"],
                        title,
                        timestamp=ts_format,
                        duration=duration,
                        file_path=file_path,
                        content_type=content_type,
                    )
                          
                else:
                    self._l.warning(
                        "station_config not available in play_file, cannot update status socket with title."
                    )
                
                                #now see if this is an autobump

                if AutoBumpAgent.is_autobump_url(file_path):
                    conf = {
                        "web_url" : AutoBumpAgent.extract_url(file_path)
                    }
                    if file_duration:
                        conf["duration"] = file_duration
                    self.show_web(conf)
                    return True

                if "panscan" in self.station_config:
                    self.mpv.panscan = self.station_config["panscan"]
                else:
                    self.mpv.panscan = 0.0

                if "video_keepaspect" in self.station_config:
                    self.mpv.keepaspect = self.station_config["video_keepaspect"]
                else:
                    self.mpv.keepaspect = True

                self._apply_vfx(datetime.datetime.now())

                # self.mpv.vf = "lavfi=[]"
                self._l.info(f"playing {file_path}")
                self.mpv.play(file_path)
                self.mpv.wait_for_property("duration")

                return True
            else:
                self._l.error(
                    f"Trying to play file {file_path} but it doesn't exist - check your configuration and try again."
                )
                return False
        except Exception as e:
            self._l.exception(e)
            self._l.error(
                f"Encountered unknown error attempting to play {file_path} - please check your configurations."
            )
            return False

    def play_file_list(self, file_list):
        """
        Play a list of audio files in random shuffle order, looping indefinitely.
        This is a simplified player for background music without duration constraints.
        Note: Does not update status socket - caller is responsible for that.

        Args:
            file_list: List of file paths to play

        Returns:
            True if playlist started successfully, False otherwise
        """
        try:
            # Filter out any files that don't exist
            valid_files = [f for f in file_list if os.path.exists(f)]

            if not valid_files:
                self._l.error("No valid audio files found in playlist")
                return False
            print(valid_files)
            # Shuffle the file list so each invocation has a different order
            random.shuffle(valid_files)

            self._l.info(f"Starting shuffle playlist with {len(valid_files)} files")

            # Clear any existing playlist and load the files
            self.current_playing_file_path = "playlist"

            # Clear existing playlist
            self.mpv.command("playlist-clear")

            # Load files using loadfile with 'append' flag
            for i, file_path in enumerate(valid_files):
                self._l.debug(f"Adding to playlist: {file_path}")
                if i == 0:
                    # First file: replace current playlist
                    self.mpv.command("loadfile", file_path, "replace")
                else:
                    # Subsequent files: append to playlist
                    self.mpv.command("loadfile", file_path, "append")

            # Set playlist to loop infinitely
            self.mpv.loop_playlist = "inf"

            # Start playback - don't wait for duration to avoid blocking channel changes
            self._l.info("Starting playlist playback")

            return True

        except Exception as e:
            self._l.exception(e)
            self._l.error(f"Error starting playlist: {e}")
            return False

    def _apply_vfx(self, current_time):
        vfx = None
        if "video_scramble_fx" in self.station_config:
            vfx = self.station_config["video_scramble_fx"]
        elif "station_fx" in self.station_config:
            vfx = "station_fx"
            self.scramble_effects["station_fx"] = self.station_config["station_fx"]

        # check if one is set on the slot and override if so
        slot = SlotReader.get_slot(self.station_config, current_time)
        if slot and "video_scramble_fx" in slot:
            if slot["video_scramble_fx"] in self.scramble_effects:
                vfx = slot["video_scramble_fx"]
            else:
                vfx = None

        if vfx:
            if vfx in self.scramble_effects:
                self.mpv.vf = self.scramble_effects[vfx]
                self.skip_reception_check = True
                if vfx == "horizontal_line":
                    self.scrambler = HLScrambledVideoFilter()
                elif vfx == "diagonal_lines":
                    self.scrambler = DiagonalScrambledVideoFilter()
                elif vfx == "color_inversion":
                    self.scrambler = ColorInvertedScrambledVideoFilter()
                elif vfx == "chunky_scramble":
                    self.scrambler = ChunkyScrambledVideoFilter()
            else:
                self._l.warning(f"Scrambler effect '{self.station_config['video_scramble_fx']}' does not exist.")
        else:
            self.skip_reception_check = False
            self.mpv.vf = ""
            self.scrambler = None

    def play_image(self, duration):
        pass

    def show_guide(self, guide_config):
        # create the pipe to communicate with the guide channel
        queue = multiprocessing.Queue()
        guide_process = multiprocessing.Process(
            target=guide_channel_runner,
            args=(
                guide_config,
                queue,
            ),
        )
        guide_process.start()

        if "play_sound" in guide_config and guide_config["play_sound"]:
            sound_to_play = guide_config["sound_to_play"]

            # Normalize sound_to_play to always be a list
            if isinstance(sound_to_play, str):
                # Check if it's a directory (with or without trailing slash)
                if os.path.isdir(sound_to_play):
                    # Find all mp3 files in the directory
                    mp3_files = glob.glob(os.path.join(sound_to_play, "*.mp3"))
                    if mp3_files:
                        sound_to_play = sorted(mp3_files)
                        self._l.info(f"Expanded directory {guide_config['sound_to_play']} to {len(sound_to_play)} mp3 files")
                    else:
                        self._l.error(f"Directory {sound_to_play} contains no mp3 files")
                        sound_to_play = []
                else:
                    # Single file - wrap in a list
                    sound_to_play = [sound_to_play]
            elif not isinstance(sound_to_play, list):
                self._l.error(f"Invalid sound_to_play configuration: {type(sound_to_play)}")
                sound_to_play = []

            # Now sound_to_play is always a list
            if len(sound_to_play) == 0:
                # No valid files
                self.mpv.stop()
                self.current_playing_file_path = None
            elif len(sound_to_play) == 1:
                # Single file - use the simple play_file method
                self._l.info(f"Playing guide audio from single file: {sound_to_play[0]}")
                playing = self.play_file(sound_to_play[0])
                if not playing:
                    self.mpv.stop()
                    self.current_playing_file_path = None
            else:
                # Multiple files - use shuffle playlist
                self._l.info(f"Playing guide audio as shuffle playlist with {len(sound_to_play)} files")
                playing = self.play_file_list(sound_to_play)
                if not playing:
                    self.mpv.stop()
                    self.current_playing_file_path = None
        else:
            self.mpv.stop()
            self.current_playing_file_path = None

        # update status
        update_status_socket(
            "playing",
            self.station_config["network_name"],
            self.station_config["channel_number"],
            self.station_config["network_name"],
            timestamp=StationManager().server_conf["date_time_format"],
            content_type="guide",
        )
        keep_going = True
        while keep_going:
            time.sleep(0.05)
            response = self.input_check_fn()
            if response:
                self._l.info("Sending the guide channel shutdown command")
                queue.put(GuideCommands.hide_window)
                guide_process.join()
                return response

        return PlayerOutcome(PlayerState.SUCCESS)

    def show_web(self, web_config):
        if not WEB_RENDER_AVAILABLE:
            self._l.error("Web rendering not available - PySide6 not installed")
            msg = "Web rendering requires PySide6 to be installed and configured. Please check documentation."
            return PlayerOutcome(PlayerState.EXIT_COMMAND, msg)

        # create the pipe to communicate with the web channel
        self.web_queue = multiprocessing.Queue()
        self.web_process = multiprocessing.Process(
            target=web_render_runner,
            args=(
                web_config,
                self.web_queue,
            ),
        )
        self.web_process.start()

        # Stop any currently playing content
        self.mpv.stop()
        self.current_playing_file_path = None

        # update status
        update_status_socket(
            "playing",
            self.station_config["network_name"],
            self.station_config["channel_number"],
            self.station_config["network_name"],
            timestamp=StationManager().server_conf["date_time_format"],
            content_type="web",
        )

        # Check if duration is specified for auto-bumps
        duration = web_config.get("duration")
        stop_time = None
        if duration:
            stop_time = datetime.datetime.now() + datetime.timedelta(seconds=duration)
            self._l.info(f"Web content will auto-stop after {duration} seconds")

        keep_going = True
        while keep_going:
            time.sleep(0.05)

            # Check if duration has expired
            if stop_time and datetime.datetime.now() >= stop_time:
                self._l.info("Web content duration expired, shutting down")
                try:
                    self.web_queue.put("hide_window")
                    self._l.info("Sent hide_window message to web process")
                    self.web_process.join(timeout=3)  # Wait up to 3 seconds
                    if self.web_process.is_alive():
                        self._l.warning("Web process did not terminate gracefully, forcing termination")
                        self.web_process.terminate()
                        self.web_process.join(timeout=1)
                    self._l.info("Web process terminated successfully")
                except Exception as e:
                    self._l.error(f"Error shutting down web process: {e}")
                finally:
                    self.web_process = None
                    self.web_queue = None
                return PlayerOutcome(PlayerState.SUCCESS)

            response = self.input_check_fn()
            if response:
                self._l.info("Sending the web channel shutdown command")
                self.web_queue.put("hide_window")
                self.web_process.join()
                self.web_process = None
                self.web_queue = None
                return response
        return PlayerOutcome(PlayerState.SUCCESS)

    def schedule_panic(self, network_name):
        self._l.critical("*********************Schedule Panic*********************")
        self._l.critical(f"Schedule not found for {network_name} - attempting to generate a one-day extention")
        schedule = LiquidSchedule(StationManager().station_by_name(network_name))
        schedule.add_days(1)
        self._l.warning(f"Schedule extended for {network_name} - reloading schedules now")
        LiquidManager().reload_schedules()

    def play_slot(self, network_name, when):
        import time
        start_time = time.perf_counter()
        liquid = LiquidManager()
        liquid_init_time = time.perf_counter() - start_time
        self._l.info(f"LiquidManager() initialization took {liquid_init_time:.3f} seconds")

        try:
            play_point = liquid.get_play_point(network_name, when)
            self._current_playing = play_point
        except (ScheduleNotFound, ScheduleQueryNotInBounds):
            self.schedule_panic(network_name)
            self._l.warning(f"Schedules reloaded - retrying play for: {network_name}")
            # fail so we can return and try again
            return PlayerOutcome(PlayerState.FAILED)
        
        if play_point is None:
            self.current_playing_file_path = None
            self.current_playing_block_title = None
            return PlayerOutcome(PlayerState.FAILED)
        
        return self._play_from_point(play_point)

    # returns true if play is interrupted
    def _play_from_point(self, play_point: PlayPoint):
        # Fade to black duration before commercial breaks (in seconds)
        FADE_DURATION = 0.5
        fade_active = False

        if len(play_point.plan):
            initial_skip = play_point.offset

            # iterate over the slice from index to end
            for entry in play_point.plan[play_point.index :]:
                self._l.info(f"Starting entry at {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
                self._l.info(f"Playing entry {entry}")
                self._l.info(f"Initial Skip: {initial_skip}")
                total_skip = entry.skip + initial_skip

                is_stream = False

                if hasattr(entry, "is_stream"):
                    is_stream = entry.is_stream

                title = play_point.block_title
                content_type = getattr(entry, 'content_type', 'feature')  # Get content_type from entry, default to 'feature'
                self.play_file(entry.path, file_duration=entry.duration, current_time=total_skip, is_stream=is_stream, title=title, content_type=content_type)

                if not is_stream:
                    try:
                        self.mpv.seek(total_skip)
                    except Exception:
                        self._l.error(f"Failed seeking {total_skip} on {entry.path}")
                        return PlayerOutcome(PlayerState.FAILED)

                    self._l.info(f"Seeking for: {total_skip}")

                # Detect if this video is being clipped (stopping before natural end)
                is_clipped = False
                try:
                    actual_file_duration = self.mpv.duration
                    stop_position = total_skip + (entry.duration - initial_skip)
                    # If stopping before end (with tolerance), we're clipping
                    is_clipped = stop_position < (actual_file_duration - 0.5)
                    self._l.info(f"File duration: {actual_file_duration:.2f}s, stop at: {stop_position:.2f}s, clipped: {is_clipped}")
                except Exception as e:
                    self._l.info(f"Could not determine if clipped: {e}")
                    is_clipped = False

                if entry.duration:
                    self._l.info(f"Monitoring for: {entry.duration - initial_skip}")

                    # Calculate target end time using wall clock
                    target_end_time = datetime.datetime.now() + datetime.timedelta(seconds=(entry.duration - initial_skip))
                    self._l.info(f"Target end time: {target_end_time.strftime('%H:%M:%S.%f')[:-3]}")

                    # this is our main event loop
                    keep_waiting = True
                    while keep_waiting:
                        if not self.skip_reception_check:
                            self.update_reception()
                        else:
                            if self.scrambler:
                                self.mpv.vf = self.scrambler.update_filter()

                        # Calculate time remaining based on wall clock
                        time_remaining = (target_end_time - datetime.datetime.now()).total_seconds()

                        # Initiate fade-to-black effect when entering fade window (only if clipped)
                        if 0 < time_remaining <= FADE_DURATION and not fade_active and is_clipped:
                            self._l.info(f"Starting fade with {time_remaining:.2f}s remaining")

                            # Use MPV's built-in fade filter with duration
                            # Fade video to black (only if not using scramble effects)
                            if not self.skip_reception_check:
                                try:
                                    # Use fade filter: fade out to black over remaining time
                                    self.mpv.vf = f"fade=t=out:st=0:d={time_remaining}"
                                except Exception as e:
                                    self._l.debug(f"Could not set video fade filter: {e}")

                            fade_active = True

                        if time_remaining <= 0:
                            keep_waiting = False
                        else:
                            # debounce time
                            time.sleep(0.05)
                            response = self.input_check_fn()
                            if response:
                                return response
                else:
                    return PlayerOutcome(PlayerState.FAILED)

                # Log timing for debugging inter-entry delays
                self._l.info(f"Segment ended at {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

                # Reset fade state for next segment
                fade_active = False

                initial_skip = 0

            self._l.info("Done playing block")
            return PlayerOutcome(PlayerState.SUCCESS)
        else:
            self.current_playing_file_path = None
            return PlayerOutcome(PlayerState.FAILED, "Failure getting index...")

    def get_current_path(self):
        if self.current_playing_file_path:
            basename = os.path.basename(self.current_playing_file_path)
            title, _ = os.path.splitext(basename)
            return title
        return None
