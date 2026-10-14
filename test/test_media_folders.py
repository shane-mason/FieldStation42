import asyncio
import pytest
from unittest.mock import patch
from fastapi import HTTPException

from fs42.fs42_server.api import media


@pytest.fixture
def project_root(tmp_path):
    root = tmp_path / "project"
    content = root / "catalog" / "station"
    for name in ["sitcoms", "movies", ".hidden"]:
        (content / name).mkdir(parents=True)
    (content / "notes.txt").write_text("not a folder")

    external = tmp_path / "external_drive"
    (external / "cartoons").mkdir(parents=True)
    (root / "linked").symlink_to(external)

    with patch.object(media, "PROJECT_ROOT", str(root)):
        yield root


def _folders(path):
    return asyncio.run(media.list_folders(path))["folders"]


def test_lists_visible_subfolders_sorted(project_root):
    assert _folders("catalog/station") == ["movies", "sitcoms"]


def test_follows_symlinked_directories_outside_root(project_root):
    assert _folders("linked") == ["cartoons"]


def test_rejects_parent_escape(project_root):
    with pytest.raises(HTTPException) as err:
        _folders("catalog/../../elsewhere")
    assert err.value.status_code == 400


def test_absolute_path_outside_root_is_listed(project_root, tmp_path):
    assert _folders(str(tmp_path / "external_drive")) == ["cartoons"]


def test_missing_directory_is_404(project_root):
    with pytest.raises(HTTPException) as err:
        _folders("catalog/nope")
    assert err.value.status_code == 404
