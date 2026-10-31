import json
from pathlib import Path

from pydantic import BaseModel
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtCore import Qt, QRectF

from fs42.station_manager import StationManager
from fs42.osd.content_classifier import ContentType, classify_current_content
from fs42.osd.osd_layout import (HAlignment, VAlignment, frac_to_margin_px, frac_to_size_px, resolve_top_left)

project_root = Path(__file__).parent.parent.parent
SOCKET_FILE = "runtime/stream_metadata.socket"


class StreamArtworkDisplayConfig(BaseModel):
    halign: HAlignment = HAlignment.CENTER
    valign: VAlignment = VAlignment.CENTER
    width: float = 0.28125
    height: float = 0.5
    x_margin: float = 0.0
    y_margin: float = 0.0
    alpha: float = 1.0


class StreamArtworkDisplay:
    def __init__(self, config: StreamArtworkDisplayConfig):
        Path("/tmp/stream_artwork_init_test.txt").write_text(
            f"StreamArtworkDisplay initialized: {__file__}\n"
        )
        
        self.config = config
        self.artwork_path = None
        self.pixmap = QPixmap()
        self.station_manager = StationManager()
        self.current_channel_info = {}
        self.channel_config = {}
        self.current_content_type = ContentType.UNKNOWN
        self.check_status()
    def check_status(self):
        try:
            socket_path = Path(SOCKET_FILE)
            if not socket_path.is_absolute():
                socket_path = project_root / socket_path

            with socket_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)

        except (OSError, json.JSONDecodeError, ValueError):
            self.artwork_path = None
            self.pixmap = QPixmap()
            return

        try:
            with (project_root / "runtime/play_status.socket").open("r") as f:
                status = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            
            return

        self.current_channel_info = status
        self.channel_config = {}

        network_name = status.get("network_name")
        if network_name:
            station = self.station_manager.station_by_name(network_name)
            if isinstance(station, dict):
                self.channel_config = station

        self.current_content_type = classify_current_content()

        artwork = metadata.get("artwork")

        if not artwork:
            self.artwork_path = None
            self.pixmap = QPixmap()
            return

        artwork_path = Path(artwork)
        if not artwork_path.is_absolute():
            artwork_path = project_root / artwork_path

        artwork_path = artwork_path.resolve()

        if str(artwork_path) == self.artwork_path:
            return

        self.artwork_path = str(artwork_path)
        pixmap = QPixmap(self.artwork_path)

        self.pixmap = pixmap if not pixmap.isNull() else QPixmap()

    def update(self, dt):
        self.check_status()

    def draw(self, painter: QPainter, screen_w: float, screen_h: float):
        if self.pixmap.isNull():
            return
        if self.channel_config.get("show_streamart", True) is False:
            return

        width = float(
            self.channel_config.get("streamart_width", self.config.width)
        )
        height = float(
            self.channel_config.get("streamart_height", self.config.height)
        )
        x_margin = float(
            self.channel_config.get("streamart_x_margin", self.config.x_margin)
        )
        y_margin = float(
            self.channel_config.get("streamart_y_margin", self.config.y_margin)
        )

        try:
            halign = HAlignment[
                self.channel_config.get(
                    "streamart_halign", self.config.halign.value
                ).upper()
            ]
        except (KeyError, AttributeError):
            halign = self.config.halign

        try:
            valign = VAlignment[
                self.channel_config.get(
                    "streamart_valign", self.config.valign.value
                ).upper()
            ]
        except (KeyError, AttributeError):
            valign = self.config.valign

        alpha = float(
            self.channel_config.get("streamart_alpha", self.config.alpha)
        )
        w = frac_to_size_px(width, screen_w)
        h = frac_to_size_px(height, screen_h)

        x_margin_px = frac_to_margin_px(x_margin, screen_w)
        y_margin_px = frac_to_margin_px(y_margin, screen_h)

        x, y = resolve_top_left(
            screen_w,
            screen_h,
            w,
            h,
            halign,
            valign,
            x_margin_px,
            y_margin_px,
        )

        # Fit the artwork inside the configured area without distorting it.
        target = QRectF(x, y, w, h)
        if w <= 0 or h <= 0:
            return
        scaled = self.pixmap.scaled(
            int(w),
            int(h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        draw_x = x + (w - scaled.width()) / 2
        draw_y = y + (h - scaled.height()) / 2
        painter.save()
        painter.setOpacity(alpha)
        painter.drawPixmap(int(draw_x), int(draw_y), scaled)
        painter.restore()
