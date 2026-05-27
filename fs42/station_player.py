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
PARENTAL_STATUS_FILE = "runtime/parental_controls.json"
PARENTAL_IMAGE_FILE = "runtime/parental_controls.ppm"

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
        ),
        "glitchtastic" : (
            "lavfi=["
            "scale=360:240:flags=fast_bilinear,"
            "format=gbrp,"
            "geq="
            "r='if(gt(pow(abs(sin(N*0.08)*sin(N*0.11)),0.15),0.7),"
            "p(mod(X+80*sin(2*PI*Y/45+N*0.4)+20*sin(2*PI*Y/13+N*0.7),W),Y),"
            "if(gt(mod(Y+N*4,H),H-30),255-p(X,Y),"
            "p(X+15*sin(2*PI*Y/45+N*0.4),Y)))':"
            "g='if(gt(pow(abs(sin(N*0.08)*sin(N*0.11)),0.15),0.7),"
            "p(mod(X+70*sin(2*PI*Y/48+N*0.43)+17*sin(2*PI*Y/14+N*0.73),W),Y),"
            "if(gt(mod(Y+N*4,H),H-30),255-p(X,Y),"
            "p(X+12*sin(2*PI*Y/48+N*0.43),Y)))':"
            "b='if(gt(pow(abs(sin(N*0.08)*sin(N*0.11)),0.15),0.7),"
            "p(mod(X+60*sin(2*PI*Y/50+N*0.46)+13*sin(2*PI*Y/15+N*0.76),W),Y),"
            "if(gt(mod(Y+N*4,H),H-30),255-p(X,Y),"
            "p(X+10*sin(2*PI*Y/50+N*0.46),Y)))'"
            ":interpolation=nearest,"
            "noise=alls=15:allf=t,"
            "eq=contrast=1.2:brightness=-0.05:saturation=1.2,"
            "format=yuv420p,"
            "scale=640:480:flags=neighbor"
            "]"
        )
    }

    audio_scramble_effects = {
        "special_sauce": "lavfi=[afreqshift=shift=-2000,vibrato=f=2.5:d=0.4,volume=0.8]",
        "the_jitters": "lavfi=[afreqshift=shift=-3000,aecho=0.6:0.5:50|80:0.4|0.3,tremolo=f=8:d=0.9,volume=0.7]",
        "possessed": "lavfi=[chorus=0.3:0.3:40|60|80:0.4|0.3|0.2:0.8|1.2|1.6:3|4|5,afreqshift=shift=-1500,lowpass=f=2500,volume=0.8]",
        "demonic": "lavfi=[rubberband=pitch=0.5,chorus=0.3:0.3:40|60:0.4|0.3:1.0|1.4:3|4,volume=1.0]",
        "slightly_borked": "lavfi=[acrusher=bits=3:samples=12:lfo=true:lforange=50:lforate=0.3,vibrato=f=3:d=0.5,volume=0.25]"
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
        self._active_afx = None
        self.parental_unlocked_network = None
        self.parental_station_name = None

    def load_up(self):
        start_time = time.perf_counter()
        liquid = LiquidManager()
        liquid_init_time = time.perf_counter() - start_time
        self._l.info(f"LiquidManager() initialization took {liquid_init_time:.3f} seconds")

    def show_text(self, text, duration=4):
        self.mpv.command("show-text", text, duration)

    def _write_parental_status(self, active, entered_count=0):
        os.makedirs(os.path.dirname(PARENTAL_STATUS_FILE), exist_ok=True)
        status = {
            "active": active,
            "network_name": self.station_config.get("network_name") if self.station_config else None,
            "channel_number": self.station_config.get("channel_number") if self.station_config else None,
            "entered_count": entered_count,
        }
        with open(PARENTAL_STATUS_FILE, "w") as fp:
            json.dump(status, fp)

    def _clear_parental_status(self):
        try:
            self._write_parental_status(False, 0)
        except Exception as e:
            self._l.debug(f"Could not clear parental controls status: {e}")

    def clear_parental_unlock(self):
        self.parental_unlocked_network = None

    PARENTAL_FONT = {
        "A": ["01110","10001","10001","11111","10001","10001","10001"],
        "B": ["11110","10001","10001","11110","10001","10001","11110"],
        "C": ["01111","10000","10000","10000","10000","10000","01111"],
        "D": ["11110","10001","10001","10001","10001","10001","11110"],
        "E": ["11111","10000","10000","11110","10000","10000","11111"],
        "F": ["11111","10000","10000","11110","10000","10000","10000"],
        "G": ["01111","10000","10000","10111","10001","10001","01111"],
        "H": ["10001","10001","10001","11111","10001","10001","10001"],
        "I": ["11111","00100","00100","00100","00100","00100","11111"],
        "J": ["00111","00010","00010","00010","10010","10010","01100"],
        "K": ["10001","10010","10100","11000","10100","10010","10001"],
        "L": ["10000","10000","10000","10000","10000","10000","11111"],
        "M": ["10001","11011","10101","10101","10001","10001","10001"],
        "N": ["10001","11001","10101","10011","10001","10001","10001"],
        "O": ["01110","10001","10001","10001","10001","10001","01110"],
        "P": ["11110","10001","10001","11110","10000","10000","10000"],
        "Q": ["01110","10001","10001","10001","10101","10010","01101"],
        "R": ["11110","10001","10001","11110","10100","10010","10001"],
        "S": ["01111","10000","10000","01110","00001","00001","11110"],
        "T": ["11111","00100","00100","00100","00100","00100","00100"],
        "U": ["10001","10001","10001","10001","10001","10001","01110"],
        "V": ["10001","10001","10001","10001","10001","01010","00100"],
        "W": ["10001","10001","10001","10101","10101","10101","01010"],
        "X": ["10001","10001","01010","00100","01010","10001","10001"],
        "Y": ["10001","10001","01010","00100","00100","00100","00100"],
        "Z": ["11111","00001","00010","00100","01000","10000","11111"],
        "0": ["01110","10001","10011","10101","11001","10001","01110"],
        "1": ["00100","01100","00100","00100","00100","00100","01110"],
        "2": ["01110","10001","00001","00010","00100","01000","11111"],
        "3": ["11110","00001","00001","01110","00001","00001","11110"],
        "4": ["00010","00110","01010","10010","11111","00010","00010"],
        "5": ["11111","10000","10000","11110","00001","00001","11110"],
        "6": ["01110","10000","10000","11110","10001","10001","01110"],
        "7": ["11111","00001","00010","00100","01000","01000","01000"],
        "8": ["01110","10001","10001","01110","10001","10001","01110"],
        "9": ["01110","10001","10001","01111","00001","00001","01110"],
        "*": ["00100","10101","01110","11111","01110","10101","00100"],
        "_": ["00000","00000","00000","00000","00000","00000","11111"],
        "-": ["00000","00000","00000","11111","00000","00000","00000"],
        "+": ["00000","00100","00100","11111","00100","00100","00000"],
        "/": ["00001","00010","00010","00100","01000","01000","10000"],
        ":": ["00000","00100","00100","00000","00100","00100","00000"],
        " ": ["00000","00000","00000","00000","00000","00000","00000"],
    }

    def _draw_rect(self, pixels, width, height, x, y, w, h, color, fill=True):
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(width, int(x + w))
        y1 = min(height, int(y + h))

        if fill:
            for yy in range(y0, y1):
                row = pixels[yy]
                for xx in range(x0, x1):
                    row[xx] = color
            return

        for xx in range(x0, x1):
            if 0 <= y0 < height:
                pixels[y0][xx] = color
            if 0 <= y1 - 1 < height:
                pixels[y1 - 1][xx] = color

        for yy in range(y0, y1):
            if 0 <= x0 < width:
                pixels[yy][x0] = color
            if 0 <= x1 - 1 < width:
                pixels[yy][x1 - 1] = color

    def _draw_text(self, pixels, width, height, text, x, y, color, scale=3):
        x_start = int(x)
        cursor_x = int(x)
        cursor_y = int(y)

        for ch in text.upper():
            if ch == "\n":
                cursor_x = x_start
                cursor_y += 9 * scale
                continue

            glyph = self.PARENTAL_FONT.get(ch, self.PARENTAL_FONT[" "])

            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit != "1":
                        continue

                    px = cursor_x + gx * scale
                    py = cursor_y + gy * scale
                    self._draw_rect(pixels, width, height, px, py, scale, scale, color, fill=True)

            cursor_x += 6 * scale

    def _write_ppm(self, path, pixels):
        height = len(pixels)
        width = len(pixels[0])

        with open(path, "wb") as fp:
            fp.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
            for row in pixels:
                for r, g, b in row:
                    fp.write(bytes((r, g, b)))

    def _render_parental_lock_screen(self, entered_count=0, message=None):
        os.makedirs(os.path.dirname(PARENTAL_IMAGE_FILE), exist_ok=True)

        width, height = 640, 480
        black = (0, 0, 0)
        gray = (172, 172, 172)
        dark_gray = (84, 84, 84)
        light_gray = (212, 212, 212)
        white = (238, 238, 238)
        text_color = (20, 20, 20)
        warning = (150, 0, 0)

        pixels = [[black for _ in range(width)] for _ in range(height)]

        # Dialog box, similar to a simple 90s/00s password prompt.
        box_x, box_y = 190, 130
        box_w, box_h = 260, 185
        self._draw_rect(pixels, width, height, box_x, box_y, box_w, box_h, gray, fill=True)
        self._draw_rect(pixels, width, height, box_x, box_y, box_w, box_h, dark_gray, fill=False)
        self._draw_rect(pixels, width, height, box_x + 3, box_y + 3, box_w - 6, box_h - 6, light_gray, fill=False)

        # Title
        self._draw_text(pixels, width, height, "ENTER PASSWORD", box_x + 42, box_y + 24, text_color, scale=2)

        # PIN boxes
        pin_y = box_y + 72
        pin_x = box_x + 62
        for i in range(4):
            x = pin_x + i * 36
            self._draw_rect(pixels, width, height, x, pin_y, 28, 30, white, fill=True)
            self._draw_rect(pixels, width, height, x, pin_y, 28, 30, dark_gray, fill=False)

            if i < entered_count:
                self._draw_rect(pixels, width, height, x + 2, pin_y + 2, 24, 26, (24, 24, 24), fill=True)
                self._draw_text(pixels, width, height, "*", x + 9, pin_y + 8, white, scale=2)

        # Divider
        self._draw_rect(pixels, width, height, box_x + 12, box_y + 120, box_w - 24, 2, dark_gray, fill=True)

        # Close / escape hint button
        self._draw_rect(pixels, width, height, box_x + 25, box_y + 135, box_w - 50, 32, gray, fill=True)
        self._draw_rect(pixels, width, height, box_x + 25, box_y + 135, box_w - 50, 32, dark_gray, fill=False)
        self._draw_text(pixels, width, height, "CH +/- TO LEAVE", box_x + 50, box_y + 145, text_color, scale=1)

        if message:
            self._draw_text(pixels, width, height, message, box_x + 58, box_y + 108, warning, scale=1)

        self._write_ppm(PARENTAL_IMAGE_FILE, pixels)

    def _show_parental_prompt_text(self, entered_count=0, message=None):
        self._render_parental_lock_screen(entered_count, message)

        image_path = os.path.abspath(PARENTAL_IMAGE_FILE)
        refresh_path = os.path.abspath(
            f"runtime/parental_controls_{entered_count}_{int(time.time() * 1000)}.ppm"
        )

        try:
            os.makedirs(os.path.dirname(refresh_path), exist_ok=True)
            with open(image_path, "rb") as src, open(refresh_path, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            self._l.warning(f"Could not refresh parental controls image: {e}")
            refresh_path = image_path

        try:
            self.mpv.command("set", "image-display-duration", "inf")
        except Exception as e:
            self._l.debug(f"Could not set image-display-duration for parental screen: {e}")

        self.mpv.command("loadfile", refresh_path, "replace")
        self.mpv.pause = False

    def _show_parental_lock_screen(self):
        self._close_now_playing()
        self.current_playing_file_path = None
        self.mpv.command("playlist-clear")
        self._show_parental_prompt_text(0)

    def _prompt_for_parental_pin(self, pin):
        entered = ""
        message = None

        self._show_parental_lock_screen()
        self._write_parental_status(True, 0)
        self._show_parental_prompt_text(0)

        try:
            while True:
                time.sleep(0.05)
                response = self.input_check_fn()

                if not response:
                    continue

                if (
                    response.status == PlayerState.SUCCESS
                    and isinstance(response.payload, str)
                    and response.payload.startswith("parental_digit:")
                ):
                    digit = response.payload.split(":", 1)[1]
                    if digit.isdigit() and len(digit) == 1:
                        entered += digit

                        if len(entered) >= len(pin):
                            if entered == pin:
                                self.parental_unlocked_network = self.station_config.get("network_name")
                                self._clear_parental_status()
                                self.show_text("UNLOCKED", 900)
                                return None

                            entered = ""
                            message = "INCORRECT PIN"
                        else:
                            message = None

                        self._write_parental_status(True, len(entered))
                        self._show_parental_prompt_text(len(entered), message)

                    continue

                if response.status == PlayerState.SUCCESS and response.payload == "parental_clear":
                    entered = ""
                    message = None
                    self._write_parental_status(True, 0)
                    self._show_parental_prompt_text(0)
                    continue

                self._clear_parental_status()
                return response
        finally:
            self._clear_parental_status()

    def _parental_controls_required(self, network_name):
        if self.parental_station_name != network_name:
            self.parental_station_name = network_name
            self.parental_unlocked_network = None

        if not self.station_config.get("parental_controls", False):
            return False

        pin = StationManager().server_conf.get("parental_controls_pin")
        if not pin:
            self._l.warning(
                "Station has parental_controls enabled, but parental_controls_pin is not configured."
            )
            return False

        return self.parental_unlocked_network != network_name

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
                    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                    web_url = AutoBumpAgent.extract_url(file_path)
                    remaining = file_duration - (current_time or 0) if file_duration else None
                    if remaining is not None:
                        parsed = urlparse(web_url)
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        params['duration'] = [str(int(remaining * 1000))]
                        web_url = urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in params.items()})))
                    conf = {
                        "web_url": web_url
                    }
                    if remaining:
                        conf["duration"] = remaining
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
        new_afx = self.audio_scramble_effects.get(afx) if afx else None
        if self._active_afx and self._active_afx != new_afx:
            self.mpv.command("af", "remove", self._active_afx)
            self._active_afx = None
        if new_afx and new_afx != self._active_afx:
            self.mpv.command("af", "add", new_afx)
            self._active_afx = new_afx
        elif afx and afx not in self.audio_scramble_effects:
            self._l.warning(f"Audio scramble effect '{afx}' does not exist.")

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

        # Refresh the active station config before any runtime station checks.
        station_config = StationManager().station_by_name(network_name)
        if station_config:
            self.station_config = station_config

        if self._parental_controls_required(network_name):
            pin = str(StationManager().server_conf.get("parental_controls_pin"))
            response = self._prompt_for_parental_pin(pin)
            if response:
                return response

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
                                if response.status == PlayerState.CHANNEL_CHANGE and self.web_process:
                                    try:
                                        self.web_queue.put("hide_window")
                                        self.web_process.join(timeout=2)
                                        if self.web_process.is_alive():
                                            self._l.warning("Web process did not terminate gracefully on channel change, forcing termination")
                                            self.web_process.terminate()
                                            self.web_process.join(timeout=1)
                                    except Exception as e:
                                        self._l.error(f"Error shutting down web process on channel change: {e}")
                                    finally:
                                        self.web_process = None
                                        self.web_queue = None
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
