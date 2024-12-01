from __future__ import annotations
import sys
import os
sys.path.append(os.getcwd())

import glob
import random
from PySide6.QtCore import QStandardPaths, Qt, Slot, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QLabel)
from PySide6.QtMultimedia import (QAudioOutput, QMediaFormat,QMediaPlayer)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

from confs.fieldStation42_conf import main_conf
from fs42.guide_builder import GuideBuilder

AVI = "video/x-msvideo"  # AVI
MP4 = 'video/mp4'

def get_random_promo():
    candidates = glob.glob("/home/wrongdog/FieldStation42/catalog/indie42_catalog/commercial/December/*.mp4")
    choice = random.choice(candidates)
    return choice

def get_supported_mime_types():
    result = []
    for f in QMediaFormat().supportedFileFormats(QMediaFormat.Decode):
        mime_type = QMediaFormat(f).mimeType()
        result.append(mime_type.name())
    return result



class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

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

        self.lbl = QLabel("FieldStation42<br>Cable Mode.")


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
        self.load_test_file()
        self._gen_styles()




    def _gen_styles(self):
        self.setStyleSheet('background-color: #00386C;')
        self.lbl.setStyleSheet("font-size: 40px; color: white;")
        self._video_widget.resize(300,200)
        #self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
        #self.setWindowFlag(Qt.FramelessWindowHint)

    def closeEvent(self, event):
        self._ensure_stopped()
        event.accept()

    def load_test_file(self):
        #url = "file:////home/wrongdog/FieldStation42/runtime/static.mp4"
        url = get_random_promo()
        self._playlist.append(url)
        self._playlist_index = len(self._playlist) - 1
        self._player.setSource(url)
        self._player.play()

    def show_status_message(self, message):
        self.statusBar().showMessage(message, 5000)

    @Slot("QMediaPlayer::Error", str)
    def _player_error(self, error, error_string):
        print(error_string, file=sys.stderr)
        self.show_status_message(error_string)

    def _ensure_stopped(self):
        if self._player.playbackState() != QMediaPlayer.StoppedState:
            self._player.stop()

if __name__ == '__main__':
    gb = GuideBuilder()
    gb.load_schedules(main_conf['stations'])
    gb.render()

    app = QApplication(sys.argv)
    main_win = MainWindow()
    #available_geometry = main_win.screen().availableGeometry()
    #main_win.resize(available_geometry.width() / 3,
    #                available_geometry.height() / 2)
    main_win.show()
    sys.exit(app.exec())
