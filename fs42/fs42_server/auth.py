import hashlib
import hmac
import logging
import re
import time
from collections import defaultdict, deque
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from fs42.station_manager import StationManager

SESSION_COOKIE = "fs42_session"
SESSION_MAX_AGE = 365 * 24 * 60 * 60
API_KEY_AUTH_ENABLED = False

LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 5 * 60

PUBLIC_PATHS = {
    "/login",
    "/logout",
    "/favicon.ico",
    "/remote",
    "/static/login.html",
    "/static/login.js",
    "/static/common.js",
    "/static/fs42_client.js",
    "/static/remote.html",
    "/stations",
    "/player/info",
    "/player/status",
    "/player/channels/guide",
    "/player/parental/clear",
    "/player/volume/up",
    "/player/volume/down",
    "/player/volume/mute",
    "/player/volume/status",
    "/player/mpv/cycle-subtitles",
    "/player/mpv/cycle-audio",
    "/manage/status",
    "/manage/restart",
    "/manage/shutdown",
}
PUBLIC_GET_PATHS = {
    "/",
    "/static/index.html",
    "/static/guide_frame.html",
    "/static/guide.css",
    "/summary",
    "/summary/",
    "/summary/channels",
    "/summary/schedules",
    "/player/status/queue_connected",
    "/schedules/all",
}
PUBLIC_GET_ROUTE_PATTERNS = (
    re.compile(r"/summary/schedules/[^/]+\Z"),
)
PUBLIC_PREFIXES = ("/static/themes/", "/static/ppv/", "/static/media_browser/")
PUBLIC_ROUTE_PATTERNS = (
    re.compile(r"/player/channels/(?:[0-9]+|up|down)\Z"),
    re.compile(r"/player/web/key/[A-Za-z0-9_]+\Z"),
    re.compile(r"/player/parental/digit/[0-9]\Z"),
    re.compile(r"/ppv/[0-9]+\Z"),
    re.compile(r"/media-browser/[0-9]+\Z"),
    re.compile(r"/media-browser/[0-9]+/tmdb\Z"),
    re.compile(r"/media-browser/[0-9]+/art/[A-Za-z0-9_-]+/.+\Z"),
    re.compile(r"/ppv/[0-9]+/control/(?:rewind|play|pause|stop|fastForward)\Z"),
)

_API_KEY_PARAM = re.compile(r"(api_key=)[^&\s\"]*")

_login_failures = defaultdict(deque)


def session_token(key):
    return hmac.new(key.encode(), b"fs42-session", hashlib.sha256).hexdigest()


def request_key(request: Request):
    if request.headers.get("x-api-key"):
        return request.headers["x-api-key"]
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("api_key")


def key_matches(candidate, key):
    return candidate is not None and hmac.compare_digest(candidate.encode(), key.encode())


def has_valid_session(request: Request, key):
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie is not None and hmac.compare_digest(cookie.encode(), session_token(key).encode())


def is_public(path, method="GET"):
    return (
        path in PUBLIC_PATHS
        or path.startswith(PUBLIC_PREFIXES)
        or any(pattern.fullmatch(path) for pattern in PUBLIC_ROUTE_PATTERNS)
        or (
            method.upper() == "GET"
            and (
                path in PUBLIC_GET_PATHS
                or any(pattern.fullmatch(path) for pattern in PUBLIC_GET_ROUTE_PATTERNS)
            )
        )
    )


def wants_html(request: Request):
    return request.method == "GET" and "text/html" in request.headers.get("accept", "")


def safe_next(next_path):
    # only same-site paths - never redirect a login to another host
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def set_session_cookie(response, key):
    response.set_cookie(
        SESSION_COOKIE,
        session_token(key),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        path="/",
    )


def client_ip(request: Request):
    return request.client.host if request.client else "unknown"


def login_blocked(request: Request, now=None):
    now = time.monotonic() if now is None else now
    failures = _login_failures[client_ip(request)]
    while failures and now - failures[0] > LOGIN_WINDOW_SECONDS:
        failures.popleft()
    return len(failures) >= LOGIN_MAX_FAILURES


def record_login_failure(request: Request, now=None):
    _login_failures[client_ip(request)].append(time.monotonic() if now is None else now)


def clear_login_failures(request: Request):
    _login_failures.pop(client_ip(request), None)


async def auth_middleware(request: Request, call_next):
    if not API_KEY_AUTH_ENABLED:
        return await call_next(request)
    key = StationManager().api_key()
    if key is None or is_public(request.url.path, request.method):
        return await call_next(request)

    if has_valid_session(request, key):
        return await call_next(request)

    if key_matches(request_key(request), key):
        response = await call_next(request)
        # a page opened with ?api_key= (kiosk, bookmark) needs the cookie for its own fetches
        if wants_html(request):
            set_session_cookie(response, key)
        return response

    if wants_html(request):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=302)
    return JSONResponse(status_code=401, content={"detail": "api key required"})


def require_admin(request: Request):
    if not API_KEY_AUTH_ENABLED:
        return
    # checked here as well as in the middleware so admin routes never depend on it alone
    key = StationManager().api_key()
    if key is None:
        raise HTTPException(status_code=403, detail="management requires api_key - see docs/API_SECURITY.md")
    if not (key_matches(request_key(request), key) or has_valid_session(request, key)):
        raise HTTPException(status_code=401, detail="api key required")


def log_security_status():
    _l = logging.getLogger("FS42SERVER")
    if not API_KEY_AUTH_ENABLED:
        _l.warning("API key authentication is disabled - all endpoints are accessible to clients that can reach this server.")
        return
    key = StationManager().api_key()
    if key is None:
        _l.warning("API security is disabled - anyone on your network can use the API. See docs/API_SECURITY.md")
    elif len(key) < 12:
        _l.warning("api_key is short and easy to guess - consider a longer one. See docs/API_SECURITY.md")
    else:
        _l.info("API security is enabled")


class ApiKeyLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = _API_KEY_PARAM.sub(r"\1***", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _API_KEY_PARAM.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args
            )
        return True
