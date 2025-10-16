import pytest
from fs42 import media_processor


def test_get_duration_with_ffprobe_success(monkeypatch):
    # ffmpeg.probe returns a dict with format.duration as string
    monkeypatch.setattr(media_processor.ffmpeg, "probe", lambda path: {"format": {"duration": "12.34"}})
    val = media_processor.MediaProcessor.get_duration_with_ffprobe("dummy.mp4")
    assert val == pytest.approx(12.34)


def test_get_duration_with_ffprobe_missing_duration(monkeypatch):
    # ffmpeg.probe returns no duration entry
    monkeypatch.setattr(media_processor.ffmpeg, "probe", lambda path: {"format": {}})
    assert media_processor.MediaProcessor.get_duration_with_ffprobe("dummy.mp4") is None


def test_get_duration_with_ffprobe_raises(monkeypatch, caplog):
    # ffmpeg.probe raises an exception -> function should return None and log/print the error
    def _raise(path):
        raise Exception("probe failed")

    monkeypatch.setattr(media_processor.ffmpeg, "probe", _raise)
    val = media_processor.MediaProcessor.get_duration_with_ffprobe("dummy.mp4")
    assert val is None
