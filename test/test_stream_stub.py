import pytest

from fs42 import stream_stub
from fs42.stream_stub import crop_to_mpv, is_stub, read_stub


def _write(tmp_path, text, name="episode.strm"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestReadStub:
    def test_url_only(self, tmp_path):
        stub = read_stub(_write(tmp_path, "https://archive.org/download/item/ep1.mp4\n"))
        assert stub == {
            "target": "https://archive.org/download/item/ep1.mp4",
            "start": 0.0,
            "duration": None,
            "crop": "",
            "aid": "auto",
        }

    def test_all_options(self, tmp_path):
        stub = read_stub(
            _write(
                tmp_path,
                "https://example.com/ep1.mp4\n#duration=1425.5\n#start=12\n#crop=640:480:40:0\n#aid=2\n",
            )
        )
        assert stub["target"] == "https://example.com/ep1.mp4"
        assert stub["duration"] == 1425.5
        assert stub["start"] == 12.0
        assert stub["crop"] == "640x480+40+0"
        assert stub["aid"] == "2"

    def test_local_path_target(self, tmp_path):
        assert read_stub(_write(tmp_path, "/media/tapes/ep1.mkv\n#duration=60\n"))["target"] == "/media/tapes/ep1.mkv"

    def test_options_before_url_and_blank_lines(self, tmp_path):
        stub = read_stub(_write(tmp_path, "\n#duration=30\n\nhttps://example.com/a.mp4\n"))
        assert stub["target"] == "https://example.com/a.mp4"
        assert stub["duration"] == 30.0

    def test_first_url_wins(self, tmp_path):
        stub = read_stub(_write(tmp_path, "https://a.example/1.mp4\nhttps://b.example/2.mp4\n"))
        assert stub["target"] == "https://a.example/1.mp4"

    def test_windows_line_endings(self, tmp_path):
        p = tmp_path / "crlf.strm"
        p.write_bytes(b"https://example.com/a.mp4\r\n#duration=10\r\n")
        stub = read_stub(str(p))
        assert stub["target"] == "https://example.com/a.mp4"
        assert stub["duration"] == 10.0

    def test_bad_values_are_ignored(self, tmp_path):
        stub = read_stub(
            _write(tmp_path, "https://example.com/a.mp4\n#duration=abc\n#start=-5\n#crop=1:2:3\n#aid=x\n#unknown=1\n")
        )
        assert stub["duration"] is None
        assert stub["start"] == 0.0
        assert stub["crop"] == ""
        assert stub["aid"] == "auto"

    def test_empty_file_has_no_target(self, tmp_path):
        assert read_stub(_write(tmp_path, ""))["target"] is None

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(OSError):
            read_stub(str(tmp_path / "nope.strm"))


def test_is_stub():
    assert is_stub("/x/y/show.strm")
    assert is_stub("SHOW.STRM")
    assert not is_stub("/x/y/show.mp4")
    assert stream_stub.STUB_EXTENSION == ".strm"


def test_crop_to_mpv():
    assert crop_to_mpv("1440:1080:240:0") == "1440x1080+240+0"
    assert crop_to_mpv("1440:1080:240") == ""
    assert crop_to_mpv("a:b:c:d") == ""
    assert crop_to_mpv("") == ""


class TestStubDuration:
    """MediaProcessor reads the length from the stub instead of probing the URL."""

    def test_duration_from_stub(self, tmp_path):
        from fs42.media_processor import MediaProcessor

        p = _write(tmp_path, "https://example.com/a.mp4\n#duration=1800\n")
        assert MediaProcessor._get_duration(p) == (1800.0, None)

    def test_missing_duration_is_reported(self, tmp_path):
        from fs42.media_processor import MediaProcessor

        duration, hint = MediaProcessor._get_duration(_write(tmp_path, "https://example.com/a.mp4\n"))
        assert duration == -1
        assert "#duration" in hint

    def test_strm_is_scanned_as_video(self, tmp_path):
        from fs42.media_processor import MediaProcessor

        _write(tmp_path, "https://example.com/a.mp4\n#duration=60\n", "a.strm")
        found = MediaProcessor._rfind_media(str(tmp_path), "video")
        assert [f.endswith("a.strm") for f in found] == [True]
