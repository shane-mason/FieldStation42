import json
import re
from pathlib import Path

from pydantic import BaseModel
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtCore import QRectF

from fs42.osd.content_classifier import ContentType, classify_current_content
from fs42.osd.osd_layout import (
    HAlignment,
    VAlignment,
    frac_to_margin_px,
    frac_to_size_px,
    resolve_top_left,
)

project_root = Path(__file__).parent.parent.parent
SOCKET_FILE = "runtime/play_status.socket"


class RatingDisplayConfig(BaseModel):
    directory: str = "runtime/ratings"
    halign: HAlignment = HAlignment.RIGHT
    valign: VAlignment = VAlignment.TOP
    width: float = 0.08
    height: float = 0.10
    x_margin: float = 0.02
    y_margin: float = 0.22
    alpha: float = 1.0
    display_time: float = 12.0
    always_show: bool = False


class RatingDisplay:
    def __init__(self, config: RatingDisplayConfig):
        self.config = config
        self.rating = None
        self.title = None
        self.network_name = None
        self.pixmap = QPixmap()
        self.time_since_change = float("inf")
        self.current_content_type = ContentType.UNKNOWN
        self.check_status()

    def normalize_rating(self, value):
        if not value:
            return None

        # Examples:
        # "US:PG / US:Rated PG" -> "PG"
        # "US:TV-14" -> "TV-14"
        value = str(value).strip().split("/")[0].strip()
        value = re.sub(r"^[A-Z]{2}:", "", value, flags=re.IGNORECASE)
        return value.strip().upper() or None

    def load_rating_image(self, rating):
        self.pixmap = QPixmap()

        if not rating:
            return

        directory = Path(self.config.directory)
        if not directory.is_absolute():
            directory = project_root / directory

        # Match the filename case-insensitively, allowing .jpg/.jpeg/.png.
        if not directory.is_dir():
            return

        for path in directory.iterdir():
            if (
                path.is_file()
                and path.suffix.lower() in (".jpg", ".jpeg", ".png")
                and path.stem.upper() == rating
            ):
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    self.pixmap = pixmap
                    return

    def check_status(self):
        try:
            with open(SOCKET_FILE, "r") as f:
                status = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            self.rating = None
            self.pixmap = QPixmap()
            self.current_content_type = ContentType.UNKNOWN
            return

        new_rating = self.normalize_rating(status.get("content_rating"))
        new_title = status.get("title")
        new_network = status.get("network_name")

        new_type = classify_current_content()

        # Restart the display timer for a new program, channel, or rating.
        if (
            new_rating != self.rating
            or new_title != self.title
            or new_network != self.network_name
        ):
            self.time_since_change = 0.0
            self.load_rating_image(new_rating)

        self.rating = new_rating
        self.title = new_title
        self.network_name = new_network
        self.current_content_type = new_type

        # Never carry a rating bug into interstitials or other non-feature content.
        if new_type != ContentType.FEATURE:
            self.pixmap = QPixmap()

        # A missing rating or missing image means there is nothing to display.
        if not new_rating:
            self.pixmap = QPixmap()

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self, painter: QPainter, screen_w: float, screen_h: float):
        if self.pixmap.isNull():
            return

        if self.current_content_type not in (
            ContentType.FEATURE,
            ContentType.STREAM,
        ):
            return

        if (
            not self.config.always_show
            and self.time_since_change >= self.config.display_time
        ):
            return

        w = frac_to_size_px(self.config.width, screen_w)
        h = frac_to_size_px(self.config.height, screen_h)
        x_margin_px = frac_to_margin_px(self.config.x_margin, screen_w)
        y_margin_px = frac_to_margin_px(self.config.y_margin, screen_h)

        x, y = resolve_top_left(
            screen_w,
            screen_h,
            w,
            h,
            self.config.halign,
            self.config.valign,
            x_margin_px,
            y_margin_px,
        )

        painter.save()
        painter.setOpacity(self.config.alpha)
        painter.drawPixmap(
            QRectF(x, y, w, h),
            self.pixmap,
            QRectF(self.pixmap.rect()),
        )
        painter.restore()
