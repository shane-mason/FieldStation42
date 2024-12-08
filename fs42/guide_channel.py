from __future__ import annotations
import sys
from pathlib import Path
import os
sys.path.append(os.getcwd())


import glob
import random
from enum import Enum

#pip3 install PyQt6
#pip3 install PyQt6-WebEngine
from PyQt6.QtCore import QStandardPaths, Qt, pyqtSlot, QTimer, QThread, QDeadlineTimer, QUrl
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QLabel)
from PyQt6.QtMultimedia import (QAudioOutput, QMediaFormat,QMediaPlayer)
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView

from confs.fieldStation42_conf import main_conf
from fs42.guide_builder import GuideBuilder



RENDER_INTERVAL = 60000

class GuideCommands:
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"

class GuideWindow(QMainWindow):

    def __init__(self, command_q, guide_config):

        super().__init__()

        self.command_q = command_q
        self.guide_config = guide_config

        #render schedule for first run
        self._render_schedule()

        #setup the webview to display the channels
        self.view = QWebEngineView(self)
        self.view.load(self.get_rendered_url())

        self._playlist = []  #
        self._playlist_index = -1
        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)

        self._player.errorOccurred.connect(self._player_error)
        self._player.playingChanged.connect(self._playing_changed)


        self._video_widget = QVideoWidget()
        self._player.setVideoOutput(self._video_widget)

        self.lbl = QLabel(self.get_random_message())


        toprow = QHBoxLayout()
        toprow.addWidget(self._video_widget)
        toprow.addWidget(self.lbl)
        layout = QVBoxLayout()
        layout.addLayout(toprow)
        layout.addWidget(self.view)

        window = QWidget();
        window.setLayout(layout);

        self.setCentralWidget(window);

        self.load_video_loops()
        self._gen_styles()

        #set timer to update schedule render
        self.render_timer = QTimer(self)
        self.render_timer.setInterval(RENDER_INTERVAL)
        self.render_timer.timeout.connect(self._render_schedule)
        self.render_timer.start()

        #set timers to listen for guide commands
        self.command_timer = QTimer(self)
        self.command_timer.setInterval(100)
        self.command_timer.timeout.connect(self._check_commands)
        self.command_timer.start()

    def _gen_styles(self):
        c = self.guide_config
        if "full_screen" not in c or c["full_screen"] is False:
            self.setGeometry(c['window_x'], c['window_y'], c['window_width'], c['window_height'])

        self.setStyleSheet('background-color: #00386C;')
        self.lbl.setStyleSheet("font-size: 30px; color: white;")
        self.lbl.setFixedWidth(390)

    def get_rendered_url(self):
        rel = f"fs42/guide_render/static/{self.guide_config['template']}"
        absolute = Path(rel).resolve()
        return QUrl(f"file:{absolute}")

    def get_random_message(self):
        if "messages" not in self.guide_config or not len(self.guide_config["messages"]):
            return "No messages<br>Check your configuration."
        random.shuffle(self.guide_config["messages"])

        if "center_messages" in self.guide_config and self.guide_config["center_messages"] == False:
            return self.guide_config['messages'][0]
        else:
            return f"<center>{self.guide_config['messages'][0]}</center>"

    def closeEvent(self, event):
        self._ensure_stopped()
        event.accept()

    def load_video_loops(self):
        urls = glob.glob(f"{self.guide_config['content_dir']}/*.mp4")
        if len(urls) == 0:
            print("No video loops found for preview channel - is this a misconfiguration?")
            return
        random.shuffle(urls)
        self._playlist = urls
        self._playlist_index = 0
        self._player.setSource(QUrl(self._playlist[self._playlist_index]))
        self._player.play()

    def _play_next(self):
        self._playlist_index+=1
        if self._playlist_index >= len(self._playlist):
            self._playlist_index = 0

        self._player.setSource(QUrl(self._playlist[self._playlist_index]))
        self._player.play()
        self.lbl.setText(self.get_random_message())

    def _playing_changed(self, playing):
        if not playing:
            self._play_next()

    def _player_error(self, error, error_string):
        print(error_string, file=sys.stderr)
        self.show_status_message(error_string)


    def _ensure_stopped(self):
        if self._player.playbackState() != QMediaPlayer.StoppedState:
            self._player.stop()

    def _check_commands(self):
        if self.command_q.qsize() > 0:
            msg = self.command_q.get_nowait()
            if msg == GuideCommands.hide_window:
                print("Got hide window command")
                guide_channel_app.quit()

    def _render_schedule(self):
        gb = GuideBuilder()
        gb.load_schedules(main_conf['stations'])
        gb.render(render_template=self.guide_config["template"], output=self.guide_config["template"])

guide_channel_app = None

def guide_channel_runner(queue, guide_config):

    global guide_channel_app
    print("Starting main window")
    guide_channel_app = QApplication(sys.argv)
    main_win = GuideWindow(queue, guide_config)
    if "full_screen" in guide_config and guide_config["full_screen"] is True:
        main_win.showFullScreen()
    else:
        main_win.show()
    print("Executing app")
    sys.exit(guide_channel_app.exec())
    print("Exiting guide")


#if __name__ == "__main__":
#    guide_channel_runner(None, None)


