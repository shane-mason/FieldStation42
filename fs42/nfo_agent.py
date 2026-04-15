import os
import json
import multiprocessing
import logging

_logger = logging.getLogger("NFOAgent")

MAX_NFO_LINES = 5

_MAIN_CONFIG_PATH = "confs/main_config.json"

_OVERLAY_DEFAULTS = {
    "overlay_effect": "outline",
    "overlay_offset_px": 2,
    "overlay_font_path": None,
    "overlay_text_color": [255, 255, 255, 255],
    "overlay_shadow_color": [0, 0, 0, 255],
    "overlay_title_size": 30,
    "overlay_body_size": 20,
    "overlay_title_weight": "bold",
    "overlay_body_weight": "normal",
    "overlay_type": "normal",
}


class NFOData:

    def __init__(self, lines):
        self.lines = lines  # list of non-empty strings, up to MAX_NFO_LINES

    @property
    def title(self):
        return self.lines[0] if self.lines else ""

    @property
    def info(self):
        return self.lines[1] if len(self.lines) > 1 else ""

    @property
    def description(self):
        return self.lines[2] if len(self.lines) > 2 else ""


DEFAULT_SHOW_SECONDS = 10


def _run_overlay_app(lines, play_duration, show_seconds, overlay_cfg):

    import sys
    import signal
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtGui import QColor, QPainter, QFont, QFontMetrics, QFontDatabase
    from PySide6.QtCore import Qt, QTimer

    effect = overlay_cfg["overlay_effect"]
    offset_px = overlay_cfg["overlay_offset_px"]
    font_path = overlay_cfg["overlay_font_path"]
    text_color = overlay_cfg["overlay_text_color"]
    shadow_color = overlay_cfg["overlay_shadow_color"]
    title_size = overlay_cfg["overlay_title_size"]
    body_size = overlay_cfg["overlay_body_size"]
    title_weight = overlay_cfg["overlay_title_weight"]
    body_weight = overlay_cfg["overlay_body_weight"]
    overlay_type = overlay_cfg["overlay_type"]

    def _qt_weight(weight_str):
        return QFont.Bold if weight_str == "bold" else QFont.Normal

    class NFOOverlayWindow(QWidget):
        def __init__(self, nfo_lines):
            super().__init__()
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_NoSystemBackground)
            self.setAutoFillBackground(False)
            self.setStyleSheet("background: transparent;")
            self.setCursor(Qt.BlankCursor)

            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.geometry()
                self.setGeometry(screen_rect)
                screen_height = screen_rect.height()
            else:
                screen_height = 1080

            self.scale = screen_height / 1080.0

            if overlay_type == "minimal":
                self.lines = nfo_lines[:2]
            else:
                self.lines = nfo_lines

            font_family = "Arial"
            if font_path and os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        font_family = families[0]

            self.title_font = QFont(font_family, int(title_size * self.scale), _qt_weight(title_weight))
            self.body_font = QFont(font_family, int(body_size * self.scale), _qt_weight(body_weight))

            self.text_color = QColor(*text_color)
            self.effect_color = QColor(*shadow_color)

        def _draw_drop_shadow(self, painter, x, y, text, font, px):
            painter.setFont(font)
            painter.setPen(self.effect_color)
            for i in range(1, px + 1):
                painter.drawText(x + i, y + i, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_outline(self, painter, x, y, text, font, px):
            painter.setFont(font)
            offsets = [
                (-px, -px), (0, -px), (px, -px),
                (-px,   0),           (px,   0),
                (-px,  px), (0,  px), (px,  px),
            ]
            painter.setPen(self.effect_color)
            for dx, dy in offsets:
                painter.drawText(x + dx, y + dy, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_text(self, painter, x, y, text, font, px):
            if effect == "drop_shadow":
                self._draw_drop_shadow(painter, x, y, text, font, px)
            else:
                self._draw_outline(painter, x, y, text, font, px)

        def paintEvent(self, event):
            if not self.lines:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)

            scale = self.scale
            margin_x = int(80 * scale)
            margin_y = int(80 * scale)
            px = max(1, int(offset_px * scale))

            title_metrics = QFontMetrics(self.title_font)
            body_metrics = QFontMetrics(self.body_font)

            title_line_h = int(title_metrics.height() * 1.2)
            body_line_h = int(body_metrics.height() * 1.2)

            # Anchor to the bottom of the screen
            total_h = title_line_h + body_line_h * (len(self.lines) - 1)
            start_y = self.height() - margin_y - total_h

            x = margin_x
            y = start_y + title_metrics.ascent()
            self._draw_text(painter, x, y, self.lines[0], self.title_font, px)

            y += title_line_h
            for line in self.lines[1:]:
                self._draw_text(painter, x, y, line, self.body_font, px)
                y += body_line_h

            painter.end()

    def signal_handler(sig, frame):
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app = QApplication(sys.argv)
    window = NFOOverlayWindow(nfo_lines=lines)
    window.show()

    # Set up show/hide timers when we know how long the clip runs.
    # Only bother if the clip is long enough to have a hidden middle section.
    if play_duration is not None and play_duration > show_seconds * 2:
        hide_timer = QTimer()
        hide_timer.setSingleShot(True)
        hide_timer.timeout.connect(window.hide)
        hide_timer.start(int(show_seconds * 1000))

        show_timer = QTimer()
        show_timer.setSingleShot(True)
        show_timer.timeout.connect(window.show)
        show_timer.start(int((play_duration - show_seconds) * 1000))

    sys.exit(app.exec())


class NFOAgent:
    """Static utility for NFO sidecar files and their now-playing overlay."""

    @staticmethod
    def _load_overlay_config():
        cfg = dict(_OVERLAY_DEFAULTS)
        try:
            if os.path.exists(_MAIN_CONFIG_PATH):
                with open(_MAIN_CONFIG_PATH, "r", encoding="utf-8") as f:
                    main_cfg = json.load(f)
                for key in _OVERLAY_DEFAULTS:
                    if key in main_cfg:
                        cfg[key] = main_cfg[key]
        except Exception as e:
            _logger.warning(f"Could not load overlay config from {_MAIN_CONFIG_PATH}: {e}")
        return cfg

    @staticmethod
    def _parse_xml_nfo(content):

        # Parse a Kodi-format <musicvideo> XML NFO string.
        # Returns an NFOData or None if the content is not a recognised music video NFO.
        # Display order: artist, title, album, year.

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return None

        if root.tag != "musicvideo":
            return None

        def get(tag):
            el = root.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        artist = get("artist")
        title = get("title")
        year = get("year") or get("premiered")[:4] or ""
        album = get("album")

        lines = [l for l in [artist, title, album, year] if l][:MAX_NFO_LINES]
        return NFOData(lines) if lines else None

    @staticmethod
    def read_nfo(file_path):

        base_path = os.path.splitext(file_path)[0]
        nfo_path = base_path + ".nfo"

        _logger.info(f"NFO check: looking for {nfo_path}")

        if not os.path.exists(nfo_path):
            _logger.info(f"NFO check: no sidecar found at {nfo_path}")
            return None

        try:
            with open(nfo_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Try Kodi XML format first
            if "<musicvideo>" in content:
                data = NFOAgent._parse_xml_nfo(content)
                if data:
                    _logger.info(f"NFO check: XML — {len(data.lines)} field(s) — '{data.title}'")
                    return data
                _logger.warning(f"NFO file {nfo_path} has <musicvideo> but could not be parsed")

            # Fall back to plain text: one field per non-empty line
            lines = [l.strip() for l in content.splitlines() if l.strip()][:MAX_NFO_LINES]
            if not lines:
                _logger.warning(f"NFO file {nfo_path} is empty")
                return None

            data = NFOData(lines)
            _logger.info(f"NFO check: plain text — {len(lines)} line(s) — '{data.title}'")
            return data
        except Exception as e:
            _logger.warning(f"Failed to read NFO file {nfo_path}: {e}")
            return None

    @staticmethod
    def show_overlay(nfo_data, play_duration=None, show_seconds=DEFAULT_SHOW_SECONDS):

        if nfo_data is None:
            return None
        try:
            overlay_cfg = NFOAgent._load_overlay_config()
            process = multiprocessing.Process(
                target=_run_overlay_app,
                args=(nfo_data.lines, play_duration, show_seconds, overlay_cfg),
                daemon=True,
            )
            process.start()
            _logger.info(
                f"NFO overlay started (pid={process.pid}) '{nfo_data.title}'"
                + (f" play_duration={play_duration:.1f}s" if play_duration else " permanent")
            )
            return process
        except Exception as e:
            _logger.error(f"Failed to start NFO overlay: {e}")
            return None

    @staticmethod
    def close_overlay(process):

        if not process or not process.is_alive():
            return
        try:
            process.terminate()
            process.join(timeout=0.2)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.1)
            _logger.debug("NFO overlay closed")
        except Exception as e:
            _logger.warning(f"Error closing NFO overlay: {e}")
