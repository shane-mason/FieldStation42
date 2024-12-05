from __future__ import annotations
import sys
import os
sys.path.append(os.getcwd())

import glob
import random
from enum import Enum

from PySide6.QtCore import QStandardPaths, Qt, Slot, QTimer, QThread, QDeadlineTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QLabel)
from PySide6.QtMultimedia import (QAudioOutput, QMediaFormat,QMediaPlayer)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

from confs.fieldStation42_conf import main_conf
from fs42.guide_builder import GuideBuilder

AVI = "video/x-msvideo"  # AVI
MP4 = 'video/mp4'


def get_supported_mime_types():
    result = []
    for f in QMediaFormat().supportedFileFormats(QMediaFormat.Decode):
        mime_type = QMediaFormat(f).mimeType()
        result.append(mime_type.name())
    return result


class GuideCommands:
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"

class GuideWindow(QMainWindow):

    def __init__(self, command_q):
        super().__init__()

        self.command_q = command_q

        #setup the webview to display the channels
        self.view = QWebEngineView(self)
        self.view.load("file:////home/wrongdog/FieldStation42/fs42/guide_render/static/90s.html")


        self._playlist = []  #
        self._playlist_index = -1
        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)

        self._player.errorOccurred.connect(self._player_error)

        self._video_widget = QVideoWidget()
        #self.setCentralWidget(self._video_widget)
        #self.setCentralWidget(layout)
        self._player.setVideoOutput(self._video_widget)

        self.lbl = QLabel("<center><b>FieldStation42</b><br>Now with Cable Mode.</center>")


        toprow = QHBoxLayout()
        toprow.addWidget(self._video_widget)
        toprow.addWidget(self.lbl)
        layout = QVBoxLayout()
        layout.addLayout(toprow)
        layout.addWidget(self.view)

        window = QWidget();
        window.setLayout(layout);

        self.setCentralWidget(window);
        self.setGeometry(0, 0, 720, 480)
        self._mime_types = []
        #TODO: need to load real playlits
        self.load_video_loops()
        self._gen_styles()

        #set timers to listen for guide commands
        self.command_timer = QTimer(self)
        self.command_timer.setInterval(500)
        self.command_timer.timeout.connect(self._check_commands)
        self.command_timer.start()

    def _gen_styles(self):
        self.setStyleSheet('background-color: #00386C;')
        self.lbl.setStyleSheet("font-size: 30px; color: white;")
        self.lbl.setFixedWidth(390)
        #self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        #self.setWindowFlag(Qt.FramelessWindowHint)

    def closeEvent(self, event):
        self._ensure_stopped()
        event.accept()

    def load_video_loops(self):
        urls = glob.glob("/home/wrongdog/FieldStation42/catalog/indie42_catalog/commercial/December/*.mp4")
        self._playlist = urls
        self._playlist_index = 0
        self._player.setSource(self._playlist[self._playlist_index])
        self._player.play()


    @Slot("QMediaPlayer::Error", str)
    def _player_error(self, error, error_string):
        print(error_string, file=sys.stderr)
        self.show_status_message(error_string)

    def show_window_command(self):
        print("Show command")

    def hide_window_command(self):
        print("Hide command")

    def exit_app_command(self):
        print("Exit command")

    def _ensure_stopped(self):
        if self._player.playbackState() != QMediaPlayer.StoppedState:
            self._player.stop()

    def _check_commands(self):
        print("Checking commands")
        if self.command_q.qsize() > 0:
            msg = self.command_q.get_nowait()
            if msg == GuideCommands.hide_window:
                print("Got hide window command")
                guide_channel_app.quit()

guide_channel_app = None

def guide_channel_runner(queue):
    global guide_channel_app
    print(queue)
    print("Starting main window")
    guide_channel_app = QApplication(sys.argv)
    main_win = GuideWindow(queue)
    main_win.show()
    print("Executing app")
    sys.exit(guide_channel_app.exec())
    print("Exiting guide")

if __name__ == '__main__':
    gb = GuideBuilder()
    gb.load_schedules(main_conf['stations'])
    gb.render()



