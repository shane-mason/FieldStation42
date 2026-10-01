from enum import Enum


class HAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


class VAlignment(Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER = "CENTER"


def frac_to_margin_px(fraction: float, screen_dim_px: float) -> float:
    return fraction * screen_dim_px / 2.0


def frac_to_size_px(fraction: float, screen_dim_px: float) -> float:
    return fraction * screen_dim_px


def resolve_top_left(
    screen_w: float,
    screen_h: float,
    content_w: float,
    content_h: float,
    halign: HAlignment,
    valign: VAlignment,
    x_margin_px: float,
    y_margin_px: float,
) -> tuple[float, float]:

    if halign == HAlignment.LEFT:
        x = x_margin_px
    elif halign == HAlignment.RIGHT:
        x = screen_w - content_w - x_margin_px
    else:  # CENTER
        x = (screen_w - content_w) / 2.0

    if valign == VAlignment.TOP:
        y = y_margin_px
    elif valign == VAlignment.BOTTOM:
        y = screen_h - content_h - y_margin_px
    else:  # CENTER
        y = (screen_h - content_h) / 2.0

    return x, y
