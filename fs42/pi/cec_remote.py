#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import threading
from time import sleep

import requests
import logging

# to use this, first install cec-client:
# apt-get install cec-utils

# IMPORTANT
# add vc4.force_hotplug=3 to /boot/firmware/cmdline.txt
# otherwise your display will randomly turn on by itself.


# We'll wrap cec-client instead of using cec/libcec directly because:
#  1) python libcec doesn't fully expose the entirety of libcec, and so
#     I have been unable to convince my connected TV that Station42 is a tuner,
#     and so the channel buttons don't work, which I'd like them to.
#  2) libCEC proper has its own python wrapper which is full-featured generated from
#     SWIG, however it doesn't ship with the raspberry pi .deb files.
#  Doing this achieves everything desired with minimal hassle.
class HdmiCecRemote:
  key_up_regex = re.compile(r"key released: .*\((\d+)\) D:(\d+)")
  power_up_regex = re.compile(r"powering on 'TV'")
  power_up_regex_alternate = re.compile(r"power status changed from '.+' to '.+on'")
  power_off_regex = re.compile(r"power status changed from '.+' to 'standby'")

  def __init__(self):
    self.cb_button = None
    self.cb_power = None
    self._logger = logging.getLogger('hdmicec_remote')

  def run_forever(self):
    with subprocess.Popen(
            [str(shutil.which("cec-client")), "-d", "31", "-t", "t"], stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
    ) as cec_client:
        for line in cec_client.stdout:
          match = self.key_up_regex.search(line)
          if match:
            keycode = int(match.groups()[0], 16)
            duration = int(match.groups()[1])
            self._logger.debug(f"Key Pressed: {CecKeypressMap.get_name_by_id(keycode)}, duration: {duration}")
            if duration > 25:
              self.cb_button(keycode)
            continue
          match = self.power_up_regex.search(line)
          if match:
            self._logger.debug(f"Display power-up detected.")
            self.cb_power(True)
            continue
          match = self.power_up_regex_alternate.search(line)
          if match:
            self._logger.debug(f"Display power-up detected.")
            self.cb_power(True)
            continue
          match = self.power_off_regex.search(line)
          if match:
            self._logger.debug(f"Display power-down detected.")
            self.cb_power(False)
            continue

class _FieldStationApi:
  @staticmethod
  def load_api_key():
    if os.getenv('FS42_API_KEY'):
      return os.getenv('FS42_API_KEY')
    main_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'confs', 'main_config.json')
    try:
      with open(main_config) as f:
        key = json.load(f).get('api_key')
        return key.strip() if isinstance(key, str) and key.strip() else None
    except (OSError, ValueError, AttributeError):
      return None

  def __init__(self):
    self.FS42_HOST = os.getenv('FS42_HOST', '127.0.0.1')
    self.FS42_PORT = os.getenv('FS42_PORT', '4242')
    self.FS42_BASE_URL = f"http://{self.FS42_HOST}:{self.FS42_PORT}"

    self.FS42_API_KEY = self.load_api_key()

    self.api = requests.Session()
    if self.FS42_API_KEY:
      self.api.headers['X-API-Key'] = self.FS42_API_KEY

  def goto_channel(self, dest):
    return self.api.get(f'{self.FS42_BASE_URL}/player/channels/{dest}')

  def get_status(self):
    return self.api.get(f'{self.FS42_BASE_URL}/player/status')

  def pause(self):
    return self.api.post(f'{self.FS42_BASE_URL}/manage/stop')

  def resume(self):
    return self.api.post(f'{self.FS42_BASE_URL}/manage/start')

  def post_parental_pin(self, number):
    return self.api.post(
      f'{self.FS42_BASE_URL}/player/parental/digit/{number}',
      timeout=2
    )

  def navigate(self, direction):
    return self.api.post(f'{self.FS42_BASE_URL}/player/web/key/{direction}', timeout=2)

class _NumberTimer:
  def __init__(self):
    self.on_complete = None
    self._timeout: threading.Timer| None = None

  def start(self, duration: float):
    existing = self._timeout
    if existing:
      existing.cancel()
    timer = threading.Timer(duration, self._timer_finished)
    timer.start()
    self._timeout = timer

  def _timer_finished(self):
    self._timeout = None
    self.on_complete()

  def is_waiting(self):
    timer = self._timeout
    return False if not timer else not timer.finished

  def complete_early(self):
    timer = self._timeout
    if timer:
      timer.cancel()
      self.on_complete()
    self._timeout = None


class CecKeypressMap:
  CEC_USER_CONTROL_CODE_SELECT = 0x00
  CEC_USER_CONTROL_CODE_UP = 0x01
  CEC_USER_CONTROL_CODE_DOWN = 0x02
  CEC_USER_CONTROL_CODE_LEFT = 0x03
  CEC_USER_CONTROL_CODE_RIGHT = 0x04
  CEC_USER_CONTROL_CODE_RIGHT_UP = 0x05
  CEC_USER_CONTROL_CODE_RIGHT_DOWN = 0x06
  CEC_USER_CONTROL_CODE_LEFT_UP = 0x07
  CEC_USER_CONTROL_CODE_LEFT_DOWN = 0x08
  CEC_USER_CONTROL_CODE_ROOT_MENU = 0x09
  CEC_USER_CONTROL_CODE_SETUP_MENU = 0x0A
  CEC_USER_CONTROL_CODE_CONTENTS_MENU = 0x0B
  CEC_USER_CONTROL_CODE_FAVORITE_MENU = 0x0C
  CEC_USER_CONTROL_CODE_EXIT = 0x0D
  # reserved: 0x0E, 0x0F
  CEC_USER_CONTROL_CODE_TOP_MENU = 0x10
  CEC_USER_CONTROL_CODE_DVD_MENU = 0x11
  # reserved: 0x12 ... 0x1C
  CEC_USER_CONTROL_CODE_NUMBER_ENTRY_MODE = 0x1D
  CEC_USER_CONTROL_CODE_NUMBER11 = 0x1E
  CEC_USER_CONTROL_CODE_NUMBER12 = 0x1F
  CEC_USER_CONTROL_CODE_NUMBER0 = 0x20
  CEC_USER_CONTROL_CODE_NUMBER1 = 0x21
  CEC_USER_CONTROL_CODE_NUMBER2 = 0x22
  CEC_USER_CONTROL_CODE_NUMBER3 = 0x23
  CEC_USER_CONTROL_CODE_NUMBER4 = 0x24
  CEC_USER_CONTROL_CODE_NUMBER5 = 0x25
  CEC_USER_CONTROL_CODE_NUMBER6 = 0x26
  CEC_USER_CONTROL_CODE_NUMBER7 = 0x27
  CEC_USER_CONTROL_CODE_NUMBER8 = 0x28
  CEC_USER_CONTROL_CODE_NUMBER9 = 0x29
  CEC_USER_CONTROL_CODE_DOT = 0x2A
  CEC_USER_CONTROL_CODE_ENTER = 0x2B
  CEC_USER_CONTROL_CODE_CLEAR = 0x2C
  CEC_USER_CONTROL_CODE_NEXT_FAVORITE = 0x2F
  CEC_USER_CONTROL_CODE_CHANNEL_UP = 0x30
  CEC_USER_CONTROL_CODE_CHANNEL_DOWN = 0x31
  CEC_USER_CONTROL_CODE_PREVIOUS_CHANNEL = 0x32
  CEC_USER_CONTROL_CODE_SOUND_SELECT = 0x33
  CEC_USER_CONTROL_CODE_INPUT_SELECT = 0x34
  CEC_USER_CONTROL_CODE_DISPLAY_INFORMATION = 0x35
  CEC_USER_CONTROL_CODE_HELP = 0x36
  CEC_USER_CONTROL_CODE_PAGE_UP = 0x37
  CEC_USER_CONTROL_CODE_PAGE_DOWN = 0x38
  # reserved: 0x39 ... 0x3F
  CEC_USER_CONTROL_CODE_POWER = 0x40
  CEC_USER_CONTROL_CODE_VOLUME_UP = 0x41
  CEC_USER_CONTROL_CODE_VOLUME_DOWN = 0x42
  CEC_USER_CONTROL_CODE_MUTE = 0x43
  CEC_USER_CONTROL_CODE_PLAY = 0x44
  CEC_USER_CONTROL_CODE_STOP = 0x45
  CEC_USER_CONTROL_CODE_PAUSE = 0x46
  CEC_USER_CONTROL_CODE_RECORD = 0x47
  CEC_USER_CONTROL_CODE_REWIND = 0x48
  CEC_USER_CONTROL_CODE_FAST_FORWARD = 0x49
  CEC_USER_CONTROL_CODE_EJECT = 0x4A
  CEC_USER_CONTROL_CODE_FORWARD = 0x4B
  CEC_USER_CONTROL_CODE_BACKWARD = 0x4C
  CEC_USER_CONTROL_CODE_STOP_RECORD = 0x4D
  CEC_USER_CONTROL_CODE_PAUSE_RECORD = 0x4E
  # reserved: 0x4F
  CEC_USER_CONTROL_CODE_ANGLE = 0x50
  CEC_USER_CONTROL_CODE_SUB_PICTURE = 0x51
  CEC_USER_CONTROL_CODE_VIDEO_ON_DEMAND = 0x52
  CEC_USER_CONTROL_CODE_ELECTRONIC_PROGRAM_GUIDE = 0x53
  CEC_USER_CONTROL_CODE_TIMER_PROGRAMMING = 0x54
  CEC_USER_CONTROL_CODE_INITIAL_CONFIGURATION = 0x55
  CEC_USER_CONTROL_CODE_SELECT_BROADCAST_TYPE = 0x56
  CEC_USER_CONTROL_CODE_SELECT_SOUND_PRESENTATION = 0x57
  # reserved: 0x58 ... 0x5F
  CEC_USER_CONTROL_CODE_PLAY_FUNCTION = 0x60
  CEC_USER_CONTROL_CODE_PAUSE_PLAY_FUNCTION = 0x61
  CEC_USER_CONTROL_CODE_RECORD_FUNCTION = 0x62
  CEC_USER_CONTROL_CODE_PAUSE_RECORD_FUNCTION = 0x63
  CEC_USER_CONTROL_CODE_STOP_FUNCTION = 0x64
  CEC_USER_CONTROL_CODE_MUTE_FUNCTION = 0x65
  CEC_USER_CONTROL_CODE_RESTORE_VOLUME_FUNCTION = 0x66
  CEC_USER_CONTROL_CODE_TUNE_FUNCTION = 0x67
  CEC_USER_CONTROL_CODE_SELECT_MEDIA_FUNCTION = 0x68
  CEC_USER_CONTROL_CODE_SELECT_AV_INPUT_FUNCTION = 0x69
  CEC_USER_CONTROL_CODE_SELECT_AUDIO_INPUT_FUNCTION = 0x6A
  CEC_USER_CONTROL_CODE_POWER_TOGGLE_FUNCTION = 0x6B
  CEC_USER_CONTROL_CODE_POWER_OFF_FUNCTION = 0x6C
  CEC_USER_CONTROL_CODE_POWER_ON_FUNCTION = 0x6D
  # reserved: 0x6E ... 0x70
  CEC_USER_CONTROL_CODE_F1_BLUE = 0x71
  CEC_USER_CONTROL_CODE_F2_RED = 0X72
  CEC_USER_CONTROL_CODE_F3_GREEN = 0x73
  CEC_USER_CONTROL_CODE_F4_YELLOW = 0x74
  CEC_USER_CONTROL_CODE_F5 = 0x75
  CEC_USER_CONTROL_CODE_DATA = 0x76
  # reserved: 0x77 ... 0xFF
  CEC_USER_CONTROL_CODE_AN_RETURN = 0x91 #return (Samsung)
  CEC_USER_CONTROL_CODE_MAX = 0x96 # also channels list (Samsung)
  CEC_USER_CONTROL_CODE_UNKNOWN = 0xFF

  @staticmethod
  def get_name_by_id(key_id):
    return next(i[0] for i in CecKeypressMap.__dict__.items() if i[1] == key_id)

  @staticmethod
  def is_number_key(key_id):
    return CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER0 <= key_id <= CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER9

  @staticmethod
  def number_key_int(key_id):
    return key_id - CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER0

class CecRemote:
  def __init__(self, remote: HdmiCecRemote, fsapi: _FieldStationApi, timer: _NumberTimer):
    self._logger = logging.getLogger("cec-remote")
    # Last channel tracking
    self.current_channel = None
    self.last_channel = None
    self.api = fsapi
    self._timer = timer
    self._timer.on_complete = self.handle_channel_number

    remote.cb_button = self.handle_key_press
    remote.cb_power = self.handle_power

    self.number_buffer = []

  def send_parental_digit_if_active(self, number):
    try:
      status_response = self.api.get_status()
      if not status_response.ok:
        return False

      status = status_response.json()
      if not status.get("awaiting_pin"):
        return False

      response = self.api.post_parental_pin(number)

      if response.ok:
        self._logger.debug(f"Parental controls PIN digit entered: {number}")
        return True

      self._logger.warning(f"Parental controls digit failed: {response.status_code}")
      return False
    except Exception as e:
      self._logger.error(f"Parental controls digit error: {e}")
      return False

  def number_pressed(self, number):
    """Handle number key presses from remote"""

    if self.send_parental_digit_if_active(number):
      return

    self.number_buffer.append(number)
    if len(self.number_buffer) >= 3:
      self._timer.complete_early()
    else:
      self._timer.start(1.0)

  def nav_key_pressed(self, key_name):
    """Forward a navigation key to the web channel (PPV, interactive guide) through the server"""

    try:
      response = self.api.navigate(key_name)
      if response.ok:
        self._logger.debug(f"Nav key {key_name} sent")
      else:
        self._logger.warning(f"Nav key {key_name} failed")
    except Exception as e:
      self._logger.error(f"Nav key {key_name} error: {e}")

  def change_channel(self, dest):
    try:
      if dest == 'last':
        if self.last_channel:
          dest = self.last_channel
        else:
          return
      response = self.api.goto_channel(dest)
      if response.ok:
        self._logger.debug(f"Channel changed success: {dest}")
        # Poll status to wait for channel change (max 1 second)
        try:
          old_channel = self.current_channel
          new_channel = None
          max_attempts = 20  # 20 attempts * 0.05s = 1 second max

          for attempt in range(max_attempts):
            sleep(0.05)
            status_response = self.api.get_status()
            if status_response.ok:
              status = status_response.json()
              new_channel = status.get('channel_number')

              # If channel changed or we have a channel number, we're done
              if new_channel != old_channel:
                break


          self._logger.debug(f"status returned channel_number={new_channel}, current_channel={self.current_channel}")
          # Only update last_channel if the channel actually changed
          if new_channel != self.current_channel and self.current_channel is not None:
            self.last_channel = self.current_channel
            self._logger.debug(f"Channel changed: {self.current_channel} -> {new_channel} (Last: {self.last_channel})")
          else:
            self._logger.debug(f"Channel unchanged: new={new_channel}, current={self.current_channel}")
          self.current_channel = new_channel
        except Exception as e:
          self._logger.debug(f"Failed to get current channel: {e}")
          self.current_channel = None
      else:
        self._logger.warning(f"Channel {dest} failed")
    except Exception as e:
      self._logger.error(f"Channel {dest} error: {e}")

  def handle_channel_number(self):
    channel_number = "".join([str(i) for i in self.number_buffer])
    self.number_buffer = []
    self.change_channel(channel_number)

  def handle_key_press(self, keycode):
    if keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_UP:
      self.change_channel("up")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_DOWN:
      self.change_channel("down")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_UP:
      self.nav_key_pressed("PageUp")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_DOWN:
      self.nav_key_pressed("PageDown")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_LEFT:
      self.nav_key_pressed("NavLeft")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_RIGHT:
      self.nav_key_pressed("NavRight")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_SELECT:
      self.nav_key_pressed("Enter")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_BACKWARD:
      self.change_channel("last")
    elif keycode == CecKeypressMap.CEC_USER_CONTROL_CODE_ELECTRONIC_PROGRAM_GUIDE:
      self.change_channel("guide")
    elif CecKeypressMap.is_number_key(keycode):
      pressed = CecKeypressMap.number_key_int(keycode)
      self.number_pressed(pressed)

  def handle_power(self, on):
    response = self.api.resume() if on else self.api.pause()
    if not response.ok:
      self._logger.warning(f"Power change failed: {response.text}")

def main(wrapper: HdmiCecRemote, fsapi: _FieldStationApi, timer: _NumberTimer = _NumberTimer()):
  remote = CecRemote(wrapper, fsapi, timer)
  try:
    wrapper.run_forever()
  except KeyboardInterrupt:
    print("Shutting down")
  return remote

if __name__ == "__main__":
  r = HdmiCecRemote()
  main(r, _FieldStationApi())
