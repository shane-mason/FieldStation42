import logging
import os
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from fs42.station_manager import StationManager
from fs42.fs42_server import auth
from fs42.fs42_server.api.player import connected_command_queue

router = APIRouter(prefix="/manage", tags=["manage"])

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
STARTED_AT = time.time()
INCOMING_LIMIT = 50

_l = logging.getLogger("FS42SERVER")

PULL_FAILURES = [
    ("would be overwritten", "local edits",
     "Files you changed locally would be overwritten by the update. Commit, move, or undo those changes, then try again."),
    ("Not possible to fast-forward", "diverged",
     "Your copy has commits that aren't upstream, so it can't be updated by a simple pull. Resolve it from a terminal."),
    ("diverg", "diverged",
     "Your copy has commits that aren't upstream, so it can't be updated by a simple pull. Resolve it from a terminal."),
    ("no tracking information", "no upstream",
     "This branch isn't tracking a remote branch, so there is nothing to pull from."),
    ("not currently on a branch", "detached",
     "The checkout isn't on a branch (detached HEAD), so there is nothing to pull."),
    ("Could not resolve host", "network", "Couldn't reach the git server. Check the network connection."),
    ("unable to access", "network", "Couldn't reach the git server. Check the network connection."),
]


def _git(*args, timeout=10):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(e))


def _git_out(*args, timeout=10):
    result = _git(*args, timeout=timeout)
    return result.stdout.strip() if result.returncode == 0 else None


def _under_systemd():
    return "INVOCATION_ID" in os.environ


def _in_docker():
    return os.path.exists("/.dockerenv")


def _active_units():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-units", "fs42*", "--state=active", "--plain", "--no-legend"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    units = []
    for line in result.stdout.splitlines():
        name = line.split()[0] if line.split() else ""
        if name.endswith(".service"):
            units.append(name)
    return units


def _git_status():
    if _git_out("rev-parse", "--is-inside-work-tree") != "true":
        return {"is_repo": False}
    branch = _git_out("rev-parse", "--abbrev-ref", "HEAD")
    head = (_git_out("log", "-1", "--format=%h%x00%cs%x00%s") or "\0\0").split("\0")
    return {
        "is_repo": True,
        "branch": None if branch == "HEAD" else branch,
        "upstream": _git_out("rev-parse", "--abbrev-ref", "@{u}"),
        "commit": head[0],
        "date": head[1],
        "subject": head[2],
        "dirty": bool(_git_out("status", "--porcelain", "--untracked-files=no")),
    }


def _update_blocker(git):
    if _in_docker():
        return "Running in Docker - update by rebuilding the image."
    if not git["is_repo"]:
        return "This install isn't a git checkout."
    if not git["branch"]:
        return "The checkout isn't on a branch."
    if not git["upstream"]:
        return "This branch isn't tracking a remote branch."
    return None


def _handoff(action, units):
    # the server lives in fs42.service's cgroup, so a direct systemctl call would be killed mid-way
    subprocess.run(
        ["systemd-run", "--user", "--collect", "--on-active=2", "systemctl", "--user", action, *units],
        capture_output=True, text=True, timeout=10, check=True,
    )


@router.get("/status")
def status():
    if StationManager().api_key() is None:
        return {"enabled": False}
    git = _git_status()
    return {
        "enabled": True,
        "systemd": _under_systemd(),
        "docker": _in_docker(),
        "units": _active_units() if _under_systemd() else [],
        "started_at": STARTED_AT,
        "git": git,
        "update_blocker": _update_blocker(git),
    }


@router.post("/restart", dependencies=[Depends(auth.require_admin)])
def restart(request: Request):
    if not _under_systemd():
        raise HTTPException(status_code=409, detail="FieldStation42 isn't running as a systemd service, so it can't restart itself.")
    units = _active_units()
    if not units:
        raise HTTPException(status_code=409, detail="No active fs42 services found.")
    _l.warning(f"manage: restart {' '.join(units)} requested from {auth.client_ip(request)}")
    _handoff("restart", units)
    return {"status": "restarting", "units": units}


@router.post("/stop", dependencies=[Depends(auth.require_admin)])
def stop(request: Request):
    _l.warning(f"manage: stop requested from {auth.client_ip(request)}")
    if _under_systemd():
        units = _active_units()
        if units:
            _handoff("stop", units)
            return {"status": "stopping", "units": units}
    connected_command_queue(request).put({"command": "exit"})
    return {"status": "stopping", "units": []}


@router.post("/update/check", dependencies=[Depends(auth.require_admin)])
def update_check():
    git = _git_status()
    blocker = _update_blocker(git)
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)
    fetch = _git("fetch", "--quiet", timeout=60)
    if fetch.returncode != 0:
        return JSONResponse(status_code=409, content=_failure(fetch.stderr))
    incoming = []
    for line in (_git_out("log", f"-{INCOMING_LIMIT}", "--format=%h%x00%s", "HEAD..@{u}") or "").splitlines():
        commit, _, subject = line.partition("\0")
        incoming.append({"commit": commit, "subject": subject})
    return {
        "branch": git["branch"],
        "upstream": git["upstream"],
        "behind": int(_git_out("rev-list", "--count", "HEAD..@{u}") or 0),
        "ahead": int(_git_out("rev-list", "--count", "@{u}..HEAD") or 0),
        "incoming": incoming,
    }


def _failure(output):
    for marker, reason, message in PULL_FAILURES:
        if marker in output:
            return {"status": "failed", "reason": reason, "message": message, "output": output.strip()}
    return {"status": "failed", "reason": "unknown", "message": "git couldn't update this install.",
            "output": output.strip()}


@router.post("/update", dependencies=[Depends(auth.require_admin)])
def update(request: Request):
    git = _git_status()
    blocker = _update_blocker(git)
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)
    _l.warning(f"manage: update of {git['branch']} requested from {auth.client_ip(request)}")
    old = _git_out("rev-parse", "HEAD")
    pull = _git("pull", "--ff-only", timeout=120)
    if pull.returncode != 0:
        _l.warning(f"manage: update failed: {pull.stderr.strip()}")
        return JSONResponse(status_code=409, content=_failure(pull.stderr + pull.stdout))
    new = _git_out("rev-parse", "HEAD")
    changed = (_git_out("diff", "--name-only", old, new) or "").splitlines() if old != new else []
    _l.warning(f"manage: updated {old[:7]} -> {new[:7]}" if old != new else "manage: already up to date")
    return {
        "status": "updated" if old != new else "current",
        "from": old[:7],
        "to": new[:7],
        "changed_files": changed,
        "requirements_changed": "requirements.txt" in changed,
    }
