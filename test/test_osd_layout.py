import pytest

from fs42.osd.osd_layout import (
    HAlignment,
    VAlignment,
    frac_to_margin_px,
    frac_to_size_px,
    resolve_top_left,
)

SCREEN_W = 1920.0
SCREEN_H = 1080.0


class TestFracConversions:
    def test_margin_is_fraction_of_half_dimension(self):
        # VolumeDisplayConfig default x_margin=0.1 on a 1920-wide screen -> 96px
        assert frac_to_margin_px(0.1, SCREEN_W) == pytest.approx(96.0)

    def test_size_is_fraction_of_full_dimension(self):
        # VolumeDisplayConfig default width=0.4 on a 1920-wide screen -> 768px
        assert frac_to_size_px(0.4, SCREEN_W) == pytest.approx(768.0)


class TestResolveTopLeft:
    CONTENT_W = 200.0
    CONTENT_H = 50.0
    X_MARGIN = 20.0
    Y_MARGIN = 10.0

    @pytest.mark.parametrize(
        "halign,valign,expected_x,expected_y",
        [
            (HAlignment.LEFT, VAlignment.TOP, 20.0, 10.0),
            (HAlignment.LEFT, VAlignment.BOTTOM, 20.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.LEFT, VAlignment.CENTER, 20.0, (1080.0 - 50.0) / 2.0),
            (HAlignment.RIGHT, VAlignment.TOP, 1920.0 - 200.0 - 20.0, 10.0),
            (HAlignment.RIGHT, VAlignment.BOTTOM, 1920.0 - 200.0 - 20.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.RIGHT, VAlignment.CENTER, 1920.0 - 200.0 - 20.0, (1080.0 - 50.0) / 2.0),
            (HAlignment.CENTER, VAlignment.TOP, (1920.0 - 200.0) / 2.0, 10.0),
            (HAlignment.CENTER, VAlignment.BOTTOM, (1920.0 - 200.0) / 2.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.CENTER, VAlignment.CENTER, (1920.0 - 200.0) / 2.0, (1080.0 - 50.0) / 2.0),
        ],
    )
    def test_all_alignment_combinations(self, halign, valign, expected_x, expected_y):
        x, y = resolve_top_left(
            SCREEN_W, SCREEN_H, self.CONTENT_W, self.CONTENT_H,
            halign, valign, self.X_MARGIN, self.Y_MARGIN,
        )
        assert x == pytest.approx(expected_x)
        assert y == pytest.approx(expected_y)

    def test_top_is_near_zero_in_qt_pixel_space(self):
        # Qt's origin is top-left/y-down, so VAlignment.TOP should anchor near y=0,
        # the opposite of the old GL NDC convention (+1 == visual top).
        _, y = resolve_top_left(
            SCREEN_W, SCREEN_H, self.CONTENT_W, self.CONTENT_H,
            HAlignment.LEFT, VAlignment.TOP, self.X_MARGIN, self.Y_MARGIN,
        )
        assert y == pytest.approx(self.Y_MARGIN)
