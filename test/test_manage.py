import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from fs42.fs42_server import auth
from fs42.fs42_server.api import manage

KEY = "correct-horse-battery-staple"


def _request(headers=None, cookies=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/manage/restart",
        "query_string": b"",
        "headers": raw,
        "client": ("10.0.0.5", 50000),
    })


@pytest.fixture
def key_on():
    manager = MagicMock()
    manager.return_value.api_key.return_value = KEY
    with patch("fs42.fs42_server.auth.StationManager", manager), \
            patch("fs42.fs42_server.api.manage.StationManager", manager):
        yield


@pytest.fixture
def key_off():
    manager = MagicMock()
    manager.return_value.api_key.return_value = None
    with patch("fs42.fs42_server.auth.StationManager", manager), \
            patch("fs42.fs42_server.api.manage.StationManager", manager):
        yield


def test_require_admin_refuses_when_no_key(key_off):
    with pytest.raises(HTTPException) as e:
        auth.require_admin(_request(headers={"X-API-Key": KEY}))
    assert e.value.status_code == 403


def test_require_admin_rejects_wrong_key(key_on):
    with pytest.raises(HTTPException) as e:
        auth.require_admin(_request(headers={"X-API-Key": "wrong"}))
    assert e.value.status_code == 401


def test_require_admin_accepts_key_and_session(key_on):
    auth.require_admin(_request(headers={"X-API-Key": KEY}))
    auth.require_admin(_request(cookies={auth.SESSION_COOKIE: auth.session_token(KEY)}))


def test_status_with_key_off(key_off):
    assert manage.status() == {"enabled": False}


def test_status_shape(key_on, monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    status = manage.status()
    assert status["enabled"] is True
    assert status["systemd"] is False
    assert status["units"] == []
    assert "is_repo" in status["git"]
    assert status["started_at"] == manage.STARTED_AT


def test_restart_needs_systemd(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    with pytest.raises(HTTPException) as e:
        manage.restart(_request())
    assert e.value.status_code == 409


def test_restart_hands_off_to_systemd_run(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "abc")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["systemctl", "--user"]:
            return subprocess.CompletedProcess(argv, 0,
                "fs42.service loaded active running FS42\n"
                "fs42-osd.service loaded active running OSD\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch("fs42.fs42_server.api.manage.subprocess.run", fake_run):
        result = manage.restart(_request())

    assert result["units"] == ["fs42.service", "fs42-osd.service"]
    handoff = calls[-1]
    assert handoff[0] == "systemd-run"
    assert handoff[-3:] == ["restart", "fs42.service", "fs42-osd.service"]


def test_stop_without_systemd_uses_player_queue(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    queue = MagicMock()
    request = _request()
    request.scope["app"] = MagicMock()
    request.app.state.player_command_queue = queue
    manage.stop(request)
    queue.put.assert_called_once_with({"command": "exit"})


# --- git, against real throwaway repos ---

def _sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _commit(cwd, name, text, message):
    with open(os.path.join(cwd, name), "w") as f:
        f.write(text)
    _sh(cwd, "add", name)
    _sh(cwd, "commit", "-q", "-m", message)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@example.invalid")
    origin = tmp_path / "origin.git"
    upstream = tmp_path / "upstream"
    install = tmp_path / "install"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(upstream)], check=True)
    _sh(upstream, "checkout", "-q", "-b", "main")
    _commit(upstream, "app.py", "v1\n", "first")
    _commit(upstream, "requirements.txt", "fastapi\n", "deps")
    _sh(upstream, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(install)], check=True)
    monkeypatch.setattr(manage, "PROJECT_ROOT", str(install))
    monkeypatch.setattr(manage, "_in_docker", lambda: False)
    return upstream, install


def _push_change(upstream, name="app.py", text="v2\n", message="second"):
    _commit(upstream, name, text, message)
    _sh(upstream, "push", "-q")


def _body(response):
    return response.status_code, json.loads(response.body)


def test_status_reports_branch_and_upstream(repos):
    git = manage._git_status()
    assert git["is_repo"] and git["branch"] == "main" and git["upstream"] == "origin/main"
    assert git["subject"] == "deps" and git["dirty"] is False


def test_check_reports_incoming(repos):
    upstream, _ = repos
    _push_change(upstream)
    check = manage.update_check()
    assert check["behind"] == 1 and check["ahead"] == 0
    assert check["incoming"][0]["subject"] == "second"


def test_update_fast_forwards(repos):
    upstream, install = repos
    _push_change(upstream, "requirements.txt", "fastapi\nuvicorn\n", "more deps")
    result = manage.update(_request())
    assert result["status"] == "updated"
    assert result["requirements_changed"] is True
    assert (install / "requirements.txt").read_text() == "fastapi\nuvicorn\n"


def test_update_when_current(repos):
    assert manage.update(_request())["status"] == "current"


def test_update_refuses_to_touch_local_edits(repos):
    upstream, install = repos
    _push_change(upstream)
    (install / "app.py").write_text("my edit\n")
    status, body = _body(manage.update(_request()))
    assert status == 409 and body["reason"] == "local edits"
    assert (install / "app.py").read_text() == "my edit\n"


def test_update_reports_diverged(repos):
    upstream, install = repos
    _push_change(upstream)
    _commit(install, "local.txt", "x\n", "local work")
    status, body = _body(manage.update(_request()))
    assert status == 409 and body["reason"] == "diverged"


def test_no_upstream_is_blocked(repos):
    _, install = repos
    _sh(install, "checkout", "-q", "-b", "feature")
    assert manage._update_blocker(manage._git_status())
    with pytest.raises(HTTPException) as e:
        manage.update(_request())
    assert e.value.status_code == 409


def test_not_a_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert manage._git_status() == {"is_repo": False}
