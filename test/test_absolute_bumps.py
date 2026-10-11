import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.catalog import ShowCatalog  # noqa: E402


def _entries(paths, tag, **_):
    return [SimpleNamespace(path=p, duration=10, tag=tag) for p in paths]


@pytest.fixture
def media(tmp_path):
    content = tmp_path / "content"
    (content / "intros").mkdir(parents=True)
    (content / "intros" / "relative.mp4").write_text("")
    elsewhere = tmp_path / "elsewhere" / "outros"
    elsewhere.mkdir(parents=True)
    (elsewhere / "a.mp4").write_text("")
    (elsewhere / "b.mp4").write_text("")
    return content, elsewhere


def _catalog(content_dir):
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = {"content_dir": str(content_dir)}
    catalog.clip_index = {"start_bumps": [], "end_bumps": []}
    catalog._l = logging.getLogger("test")
    catalog._ShowCatalog__fluid_builder = None
    return catalog


@patch("fs42.catalog.MediaProcessor._process_media", side_effect=_entries)
def test_relative_bump_dir_resolves_under_content_dir(_, media):
    content, _elsewhere = media
    catalog = _catalog(content)
    catalog._ShowCatalog__bump_collector("start_bumps", "intros")
    assert [b.path for b in catalog.clip_index["start_bumps"]] == [f"{content}/intros/relative.mp4"]
    assert catalog.get_start_bump("intros")["path"] == f"{content}/intros/relative.mp4"


@patch("fs42.catalog.MediaProcessor._process_media", side_effect=_entries)
def test_absolute_bump_dir_is_used_as_is(_, media):
    content, elsewhere = media
    catalog = _catalog(content)
    catalog._ShowCatalog__bump_collector("end_bumps", str(elsewhere))
    found = sorted(b.path for b in catalog.clip_index["end_bumps"])
    assert found == [str(elsewhere / "a.mp4"), str(elsewhere / "b.mp4")]
    assert catalog.get_end_bump(f"{elsewhere}/")["path"] in found


@patch("fs42.catalog.MediaProcessor._process_media", side_effect=_entries)
def test_absolute_bump_file_is_used_as_is(_, media):
    content, elsewhere = media
    catalog = _catalog(content)
    target = str(elsewhere / "a.mp4")
    catalog._ShowCatalog__bump_collector("start_bumps", target)
    assert catalog.get_start_bump(target)["path"] == target


@patch("fs42.catalog.MediaProcessor._process_media", side_effect=_entries)
def test_nested_relative_bump_dir_is_found(_, media):
    content, _elsewhere = media
    nested = content / "bumps" / "intros"
    nested.mkdir(parents=True)
    (nested / "nested.mp4").write_text("")
    catalog = _catalog(content)
    catalog._ShowCatalog__bump_collector("start_bumps", "bumps/intros")
    assert catalog.get_start_bump("bumps/intros")["path"] == f"{content}/bumps/intros/nested.mp4"
    assert catalog.get_start_bump("bumps/intros/")["path"] == f"{content}/bumps/intros/nested.mp4"
