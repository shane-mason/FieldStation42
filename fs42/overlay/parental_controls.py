import sys
import signal
import multiprocessing
from queue import Empty

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtCore import Qt, QRect, QTimer


THEMES = {
    "classic": {
        "screen": QColor(0, 0, 0, 0),
        "box": QColor(12, 20, 38, 235),
        "border": QColor(230, 230, 230),
        "pin_box": QColor(0, 0, 0, 170),
        "text": QColor(255, 255, 255),
        "muted": QColor(190, 190, 190),
        "message": QColor(220, 220, 220),
        "error": QColor(255, 210, 210),
    },
    "modern": {
        "screen": QColor(0, 0, 0, 0),
        "box": QColor(28, 28, 34, 235),
        "border": QColor(90, 170, 255),
        "pin_box": QColor(14, 14, 18, 210),
        "text": QColor(255, 255, 255),
        "muted": QColor(205, 205, 205),
        "message": QColor(225, 225, 225),
        "error": QColor(255, 120, 120),
    },
    "minimal": {
        "screen": QColor(0, 0, 0, 0),
        "box": QColor(245, 245, 245, 235),
        "border": QColor(40, 40, 40),
        "pin_box": QColor(255, 255, 255, 220),
        "text": QColor(20, 20, 20),
        "muted": QColor(80, 80, 80),
        "message": QColor(50, 50, 50),
        "error": QColor(160, 0, 0),
    },
}


class ParentalControlsWindow(QWidget):
    def __init__(self, network_name, queue, theme_name="classic", parent=None):
        super().__init__(parent)
        self.network_name = network_name
        self.queue = queue
        self.theme = THEMES.get(theme_name, THEMES["classic"])
        self.digits = 0
        self.error = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.BlankCursor)

        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.geometry()
            self.scale_factor = screen_rect.height() / 1080.0
        else:
            screen_rect = QRect(0, 0, 1920, 1080)
            self.scale_factor = 1.0

        self.box_width = self.scaled(560)
        self.box_height = self.scaled(280)
        box_x = screen_rect.x() + (screen_rect.width() - self.box_width) // 2
        box_y = screen_rect.y() + (screen_rect.height() - self.box_height) // 2
        self.setGeometry(box_x, box_y, self.box_width, self.box_height)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_queue)
        self.timer.start(50)

    def poll_queue(self):
        try:
            while True:
                message = self.queue.get_nowait()
                if message.get("close"):
                    QApplication.quit()
                    return

                self.digits = int(message.get("digits", self.digits))
                self.error = bool(message.get("error", False))
                self.update()
        except Empty:
            pass

    def scaled(self, value):
        return int(value * self.scale_factor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        theme = self.theme
        box_rect = QRect(0, 0, self.width() - 1, self.height() - 1)

        painter.setPen(QPen(theme["border"], self.scaled(3)))
        painter.setBrush(theme["box"])
        painter.drawRoundedRect(box_rect, self.scaled(14), self.scaled(14))

        title_font = QFont("Arial", self.scaled(28), QFont.Bold)
        body_font = QFont("Arial", self.scaled(18))
        pin_font = QFont("Arial", self.scaled(30), QFont.Bold)

        painter.setPen(theme["text"])
        painter.setFont(title_font)
        painter.drawText(
            QRect(0, self.scaled(28), self.width(), self.scaled(42)),
            Qt.AlignCenter,
            "PARENTAL CONTROLS",
        )

        painter.setFont(body_font)
        painter.drawText(
            QRect(
                self.scaled(40),
                self.scaled(88),
                self.width() - self.scaled(80),
                self.scaled(36),
            ),
            Qt.AlignCenter,
            f"{self.network_name} requires a PIN.",
        )

        message = "Incorrect PIN. Try again." if self.error else "Enter PIN to continue."
        painter.setPen(theme["error"] if self.error else theme["message"])
        painter.drawText(
            QRect(
                self.scaled(40),
                self.scaled(122),
                self.width() - self.scaled(80),
                self.scaled(34),
            ),
            Qt.AlignCenter,
            message,
        )

        pin_box_size = self.scaled(48)
        pin_gap = self.scaled(18)
        total_pin_width = (pin_box_size * 4) + (pin_gap * 3)
        start_x = (self.width() - total_pin_width) // 2
        pin_y = self.scaled(168)

        painter.setFont(pin_font)
        for index in range(4):
            rect = QRect(
                start_x + index * (pin_box_size + pin_gap),
                pin_y,
                pin_box_size,
                pin_box_size,
            )
            painter.setPen(QPen(theme["border"], self.scaled(2)))
            painter.setBrush(theme["pin_box"])
            painter.drawRoundedRect(rect, self.scaled(6), self.scaled(6))

            if index < self.digits:
                painter.setPen(theme["text"])
                painter.drawText(rect, Qt.AlignCenter, "*")

        painter.setFont(QFont("Arial", self.scaled(14)))
        painter.setPen(theme["muted"])
        painter.drawText(
            QRect(
                self.scaled(40),
                self.scaled(232),
                self.width() - self.scaled(80),
                self.scaled(28),
            ),
            Qt.AlignCenter,
            "Use channel up/down to leave this station.",
        )

        painter.end()


def signal_handler(sig, frame):
    QApplication.quit()


def run_parental_controls_app(network_name, queue, theme_name="classic"):
    signal.signal(signal.SIGINT, signal_handler)

    app = QApplication(sys.argv)
    window = ParentalControlsWindow(network_name, queue, theme_name)
    window.show()
    window.raise_()

    sys.exit(app.exec())


def run_parental_controls(network_name, queue, theme_name="classic"):
    def parental_controls_process():
        run_parental_controls_app(network_name, queue, theme_name)

    process = multiprocessing.Process(target=parental_controls_process)
    process.start()
    return process


if __name__ == "__main__":
    queue = multiprocessing.Queue()
    queue.put({"digits": 0, "error": False})
    run_parental_controls_app("LOCKED STATION", queue)
