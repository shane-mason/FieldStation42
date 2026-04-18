from enum import Enum
import logging

import multiprocessing
import time
import datetime
import json
import os
import glob
import random
import logging
import time
from python_mpv_jsonipc import MPV

from fs42.guide_tk import guide_channel_runner, GuideCommands
from fs42.autobump_agent import AutoBumpAgent

# Try to import web_render_runner, but handle gracefully if PySide6 isn't available
try:
    logging.getLogger().warning("Attempting PySide Import:")
    from fs42.webrender.web_render import web_render_runner
    WEB_RENDER_AVAILABLE = True
except ImportError as e:
    logging.getLogger().exception("ERROR LOADING PYSIDE", e)

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
    PLAY_FILE = 6


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
        "spicy" : (
            "lavfi=["
            "scale=720:480:flags=fast_bilinear,"
            "noise=alls=12:allf=t,"
            "eq=contrast=1.10:brightness=-0.04:saturation=2.4,"
            "geq="
            "r='p(X + 40*sin(2*PI*Y/60) + 12*sin(2*PI*N/10), Y)':"
            "g='p(X + 32*sin(2*PI*Y/64) + 10*sin(2*PI*N/11), Y)':"
            "b='p(X + 24*sin(2*PI*Y/68) +  8*sin(2*PI*N/12), Y)',"
            "scale=640:480:flags=neighbor"
            "]"
        ),
        "special_sauce" : (
            "lavfi=["
            "scale=360:240:flags=fast_bilinear,"
            "format=gbrp,"
            "geq="
            "r='p(mod(X + 80*sin(2*PI*Y/45 + N*0.4) + 20*sin(2*PI*Y/13 + N*0.7),W), Y)':"
            "g='p(mod(X + 70*sin(2*PI*Y/48 + N*0.43) + 17*sin(2*PI*Y/14 + N*0.73),W), Y)':"
            "b='p(mod(X + 60*sin(2*PI*Y/50 + N*0.46) + 13*sin(2*PI*Y/15 + N*0.76),W), Y)'"
            ":interpolation=nearest,"
            "noise=alls=15:allf=t,"
            "eq=contrast=1.2:brightness=-0.05:saturation=1.2,"
            "format=yuv420p,"
            "scale=640:480:flags=neighbor"
            "]"
        )
    }

    audio_scramble_effects = {
        "special_sauce": "lavfi=[afreqshift=shift=-2000,vibrato=f=2.5:d=0.4,volume=0.8]"
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
                hr_seek="yes",
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
        self.now_playing_process = None
        self.schedule_lock = None

    def load_up(self):
        start_time = time.perf_counter()
        liquid = LiquidManager()
        liquid_init_time = time.perf_counter() - start_time
        self._l.info(f"LiquidManager() initialization took {liquid_init_time:.3f} seconds")

    def show_text(self, text, duration=4):
        self.mpv.command("show-text", text, duration)

    def _close_now_playing(self):
        # terminate the Now Playing overlay if it's running
        if self.now_playing_process and self.now_playing_process.is_alive():
            try:
                self.now_playing_process.terminate()
                self.now_playing_process.join(timeout=0.2)

                # Force kill if still alive
                if self.now_playing_process.is_alive():
                    self.now_playing_process.kill()
                    self.now_playing_process.join(timeout=0.1)

                self._l.debug("Closed Now Playing overlay")
            except Exception as e:
                self._l.warning(f"Error terminating overlay: {e}")

            self.now_playing_process = None

    def _show_now_playing(self, file_path):
        # show the Now Playing overlay for an audio file
        import time
        self._close_now_playing()
        # give a brief moment for cleanup
        time.sleep(0.1)

        # Start new overlay
        try:
            from fs42.overlay.now_playing import run_now_playing
            db_path = StationManager().server_conf["db_path"]
            self.now_playing_process = run_now_playing(file_path, db_path)
            self._l.info(f"Started Now Playing overlay for {file_path}")
        except Exception as e:
            self._l.error(f"Failed to start Now Playing overlay: {e}")

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

        # Terminate any running now playing overlay
        self._l.info("Terminating now playing overlay")
        self._close_now_playing()

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

    def play_file(self, file_path, file_duration=None, current_time=None, is_stream=False, title="Unknown", content_type=None, media_type=None):
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
                    self.show_web(conf, blocking=False)
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
                self.mpv.command("playlist-clear")
                self.mpv.play(file_path)
                
                
                # Wait for video to load with timeout to prevent blocking on invalid streams.
                # We wait for time_pos (not just duration) because duration can be populated
                # from file headers before the demuxer is ready to seek — time_pos being
                # non-None means MPV has actually started decoding and a seek will be honored.
                timeout_seconds = StationManager().server_conf.get("video_seek_timeout", 10)
                start_time = time.time()

                while True:
                    try:
                        if self.mpv.time_pos is not None:
                            break
                        if time.time() - start_time > timeout_seconds:
                            self._l.error(f"Timeout waiting for playback to start on {file_path}")
                            return False
                        time.sleep(0.05)
                    except Exception as e:
                        if time.time() - start_time > timeout_seconds:
                            self._l.error(f"Error waiting for playback: {e}")
                            return False
                        time.sleep(0.05)

                # Perform seek if needed (before showing overlay)
                if not is_stream and current_time is not None and current_time > 0:
                    try:
                        self.mpv.command("seek", current_time, "absolute")
                        self._l.info(f"Seeking to: {current_time}")
                    except Exception as e:
                        self._l.error(f"Failed seeking {current_time} on {file_path}: {e}")

                # Show Now Playing overlay for audio feature files
                self._l.info(f"Media type: {media_type}, Content type: {content_type}")
                if media_type == 'audio' and content_type == 'feature':
                    self._show_now_playing(file_path)
                elif media_type == 'video':
                    # Always close any existing overlay when a new video starts,
                    # then spawn a new one only if this video has an NFO sidecar.
                    self._close_now_playing()
                    try:
                        from fs42.nfo_agent import NFOAgent
                        nfo_data = NFOAgent.read_nfo(file_path)
                        if nfo_data:
                            play_duration = None
                            if file_duration is not None:
                                play_duration = file_duration - (current_time or 0)
                            self.now_playing_process = NFOAgent.show_overlay(nfo_data, play_duration=play_duration)
                    except Exception as e:
                        self._l.warning(f"Could not start NFO overlay: {e}")

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

    def play_and_wait(self, file_path):
        self._l.info(f"Play and wait on file {file_path}")
        self._close_now_playing()
        self.mpv.vf = ""
        self.mpv.af = ""
        self.mpv.command("playlist-clear")
        self.mpv.command("loadfile", file_path, "replace")
        self.mpv.loop_playlist = "inf"
        self.current_playing_file_path = file_path

        # show NFO overlay if a sidecar file exists alongside the video
        try:
            from fs42.nfo_agent import NFOAgent
            nfo_data = NFOAgent.read_nfo(file_path)
            if nfo_data:
                self.now_playing_process = NFOAgent.show_overlay(nfo_data)
        except Exception as e:
            self._l.warning(f"Could not start NFO overlay: {e}")

        # this will keep going until channel change or other interrupt
        while True:
            time.sleep(0.05)
            response = self.input_check_fn()
            if response:
                self._close_now_playing()
                return response

    def play_file_list(self, file_list):

        try:
            # Filter out any files that don't exist
            valid_files = [f for f in file_list if os.path.exists(f)]

            if not valid_files:
                self._l.error("No valid audio files found in playlist")
                return False
    
            random.shuffle(valid_files)

            self._l.info(f"Starting shuffle playlist with {len(valid_files)} files")

            # Clear any existing playlist and load the files
            self.current_playing_file_path = "playlist"

            self.mpv.command("playlist-clear")

            # Load files using loadfile with 'append' flag
            for i, file_path in enumerate(valid_files):
                self._l.debug(f"Adding to playlist: {file_path}")
                if i == 0:
                    self.mpv.command("loadfile", file_path, "replace")
                else:
                    self.mpv.command("loadfile", file_path, "append")

            self.mpv.loop_playlist = "inf"
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

        # Apply audio scramble filter if configured
        afx = None
        if "audio_scramble_fx" in self.station_config:
            afx = self.station_config["audio_scramble_fx"]
        if slot and "audio_scramble_fx" in slot:
            afx = slot["audio_scramble_fx"]
        if afx:
            if afx in self.audio_scramble_effects:
                self.mpv.af = self.audio_scramble_effects[afx]
            else:
                self._l.warning(f"Audio scramble effect '{afx}' does not exist.")
        else:
            self.mpv.af = ""

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



    def show_web(self, web_config, blocking=True):
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

        if not blocking:
            return PlayerOutcome(PlayerState.SUCCESS)

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
                # Check if this is a web_key command - forward to web process
                if response.payload and isinstance(response.payload, str) and response.payload.startswith("web_key:"):
                    key_name = response.payload[8:]
                    if self.web_queue:
                        self.web_queue.put(f"key:{key_name}")
                        self._l.info(f"Forwarded key '{key_name}' to web process")
                else:
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
        if self.schedule_lock:
            self.schedule_lock.acquire()
        try:
            schedule = LiquidSchedule(StationManager().station_by_name(network_name))
            schedule.add_days(1)
            self._l.warning(f"Schedule extended for {network_name} - reloading schedules now")
            LiquidManager().reload_schedules()
        except Exception as e:
            self._l.error(f"Schedule panic failed for {network_name}: {e}")
        finally:
            if self.schedule_lock:
                self.schedule_lock.release()

    def play_slot(self, network_name, when):
        liquid = LiquidManager()

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

    def _play_from_point(self, play_point: PlayPoint):
        # Fade to black duration before commercial breaks (in seconds)
        FADE_DURATION = 0.5
        fade_active = False

        # Close any existing now playing overlay when starting a new play point
        # This handles channel changes and ensures clean state
        self._close_now_playing()

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
                media_type = getattr(entry, 'media_type', 'video')  # Get media_type from entry, default to 'video'
                worked = self.play_file(entry.path, file_duration=entry.duration, current_time=total_skip, is_stream=is_stream, title=title, content_type=content_type, media_type=media_type)
                if not worked:
                    return PlayerOutcome(PlayerState.FAILED)
                # Seek now happens inside play_file() before overlay is shown

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
                            if self.web_process:
                                try:
                                    self.web_queue.put("hide_window")
                                    self.web_process.join(timeout=3)
                                    if self.web_process.is_alive():
                                        self._l.warning("Web process did not terminate gracefully, forcing termination")
                                        self.web_process.terminate()
                                        self.web_process.join(timeout=1)
                                except Exception as e:
                                    self._l.error(f"Error shutting down web process: {e}")
                                finally:
                                    self.web_process = None
                                    self.web_queue = None
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
