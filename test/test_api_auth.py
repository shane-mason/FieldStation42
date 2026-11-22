import asyncio
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from fs42 import api_key_setup
from fs42.fs42_server import auth
from fs42.fs42_server.api import media

KEY = "correct-horse-battery-staple"


def _request(path="/summary", query="", headers=None, method="GET", client="10.0.0.5"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode(),
        "headers": raw,
        "client": (client, 50000),
    })


def _run(request, key=KEY):
    async def call_next(_):
        return Response("ok")

    manager = MagicMock()
    manager.return_value.api_key.return_value = key
    with patch("fs42.fs42_server.auth.StationManager", manager):
        return asyncio.run(auth.auth_middleware(request, call_next))


HTML = {"Accept": "text/html,application/xhtml+xml"}


@pytest.fixture(autouse=True)
def _clear_failures():
    auth._login_failures.clear()
    yield
    auth._login_failures.clear()


def test_security_off_allows_everything():
    assert _run(_request(), key=None).status_code == 200


@pytest.mark.parametrize("request_kwargs", [
    {"query": f"api_key={KEY}"},
    {"headers": {"X-API-Key": KEY}},
    {"headers": {"Authorization": f"Bearer {KEY}"}},
])
def test_each_key_form_is_accepted(request_kwargs):
    assert _run(_request(**request_kwargs)).status_code == 200


@pytest.mark.parametrize("request_kwargs", [
    {},
    {"query": "api_key=wrong"},
    {"headers": {"X-API-Key": "wrong"}},
    {"headers": {"Authorization": "Bearer wrong"}},
])
def test_missing_or_wrong_key_is_401(request_kwargs):
    response = _run(_request(**request_kwargs))
    assert response.status_code == 401
    assert json.loads(response.body) == {"detail": "api key required"}


def test_session_cookie_is_accepted():
    cookie = f"{auth.SESSION_COOKIE}={auth.session_token(KEY)}"
    assert _run(_request(headers={"Cookie": cookie})).status_code == 200


def test_session_from_old_key_is_rejected():
    cookie = f"{auth.SESSION_COOKIE}={auth.session_token('old-key')}"
    assert _run(_request(headers={"Cookie": cookie})).status_code == 401


@pytest.mark.parametrize("path", ["/login", "/logout", "/favicon.ico", "/static/login.html",
                                  "/static/login.js", "/static/common.js", "/static/themes/default.css"])
def test_public_paths_need_no_key(path):
    assert _run(_request(path)).status_code == 200


def test_unauthenticated_page_load_redirects_to_login():
    response = _run(_request("/static/catalog.html", query="station=abc", headers=HTML))
    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=%2Fstatic%2Fcatalog.html%3Fstation%3Dabc"


def test_page_opened_with_key_gets_session_cookie():
    response = _run(_request("/static/customguide/customguide.html", query=f"api_key={KEY}", headers=HTML))
    assert response.status_code == 200
    assert f"{auth.SESSION_COOKIE}={auth.session_token(KEY)}" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_api_call_with_key_sets_no_cookie():
    response = _run(_request(headers={"X-API-Key": KEY}))
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("next_path, expected", [
    ("/static/catalog.html", "/static/catalog.html"),
    ("//evil.example", "/"),
    ("https://evil.example", "/"),
    ("", "/"),
])
def test_safe_next_stays_on_site(next_path, expected):
    assert auth.safe_next(next_path) == expected


def test_login_blocks_after_too_many_failures():
    request = _request("/login", method="POST")
    for i in range(auth.LOGIN_MAX_FAILURES):
        assert not auth.login_blocked(request, now=100)
        auth.record_login_failure(request, now=100)
    assert auth.login_blocked(request, now=100)
    assert not auth.login_blocked(request, now=100 + auth.LOGIN_WINDOW_SECONDS + 1)


def test_login_failures_are_per_client():
    for _ in range(auth.LOGIN_MAX_FAILURES):
        auth.record_login_failure(_request(client="10.0.0.5"), now=100)
    assert not auth.login_blocked(_request(client="10.0.0.6"), now=100)


def test_access_log_masks_key():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("10.0.0.5:5000", "GET", f"/player/status?api_key={KEY}&x=1", "1.1", 200), None)
    auth.ApiKeyLogFilter().filter(record)
    assert KEY not in record.getMessage()
    assert "api_key=***&x=1" in record.getMessage()


@pytest.fixture
def media_root(tmp_path):
    root = tmp_path / "project"
    (root / "confs").mkdir(parents=True)
    (root / "confs" / "main_config.json").write_text(json.dumps({"api_key": KEY}))
    (root / "confs" / "messages.json").write_text("[]")
    (root / "alias").symlink_to(root / "confs")
    with patch.object(media, "PROJECT_ROOT", str(root)):
        yield root


@pytest.mark.parametrize("path", ["confs/main_config.json", "alias/main_config.json", "confs/../confs/main_config.json"])
def test_media_json_refuses_main_config(media_root, path):
    with pytest.raises(HTTPException) as err:
        asyncio.run(media.serve_json(path))
    assert err.value.status_code == 403


def test_media_json_still_serves_other_conf_json(media_root):
    response = asyncio.run(media.serve_json("confs/messages.json"))
    assert response.path.endswith("messages.json")


def _main_config(root):
    return json.loads((root / "confs" / "main_config.json").read_text())


def test_setup_fresh_install_generates_key(tmp_path):
    (tmp_path / "confs" / "examples").mkdir(parents=True)
    (tmp_path / "confs" / "examples" / "abc.json").write_text("{}")
    assert api_key_setup.setup(str(tmp_path), interactive=False) == "generated"
    assert len(_main_config(tmp_path)["api_key"]) >= 16


@pytest.mark.parametrize("marker", ["confs/abc.json", "runtime/fs42_fluid.db"])
def test_setup_existing_install_without_main_config_is_untouched(tmp_path, marker):
    (tmp_path / marker).parent.mkdir(parents=True)
    (tmp_path / marker).write_text("{}")
    assert api_key_setup.setup(str(tmp_path), interactive=False) == "skipped"
    assert not (tmp_path / "confs" / "main_config.json").exists()


def test_setup_existing_main_config_non_interactive_is_untouched(tmp_path):
    (tmp_path / "confs").mkdir()
    original = '{"server_port": 4242}'
    (tmp_path / "confs" / "main_config.json").write_text(original)
    assert api_key_setup.setup(str(tmp_path), interactive=False) == "skipped"
    assert (tmp_path / "confs" / "main_config.json").read_text() == original


@pytest.fixture
def existing_install(tmp_path):
    (tmp_path / "confs").mkdir()
    (tmp_path / "confs" / "abc.json").write_text("{}")
    (tmp_path / "confs" / "main_config.json").write_text('{"server_port": 4343, "parental_controls_pin": "1234"}')
    with patch("sys.stdin.isatty", return_value=True):
        yield tmp_path


def test_setup_existing_install_declined(existing_install):
    with patch("builtins.input", return_value=""):
        assert api_key_setup.setup(str(existing_install)) == "declined"
    assert "api_key" not in _main_config(existing_install)


def test_setup_existing_install_eof_is_no(existing_install):
    with patch("builtins.input", side_effect=EOFError):
        assert api_key_setup.setup(str(existing_install)) == "declined"


def test_setup_existing_install_enabled_keeps_settings(existing_install):
    with patch("builtins.input", return_value="y"):
        assert api_key_setup.setup(str(existing_install)) == "enabled"
    conf = _main_config(existing_install)
    assert conf["server_port"] == 4343
    assert conf["parental_controls_pin"] == "1234"
    assert conf["api_key"]


def test_setup_already_keyed_is_untouched(tmp_path):
    (tmp_path / "confs").mkdir()
    original = '{"api_key": "mine"}'
    (tmp_path / "confs" / "main_config.json").write_text(original)
    assert api_key_setup.setup(str(tmp_path)) == "already"
    assert (tmp_path / "confs" / "main_config.json").read_text() == original
