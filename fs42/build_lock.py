import contextlib
import logging
import os
import re
import threading
import time

from fs42.station_manager import StationManager

POLL_INTERVAL = 0.25

if os.name == "nt":
    import msvcrt

    def _try_lock(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


class BuildLockTimeout(Exception):
    pass


_held = threading.local()


def _held_by_this_thread():
    if not hasattr(_held, "names"):
        _held.names = set()
    return _held.names


def _lock_path(network_name):
    db_path = StationManager().server_conf["db_path"]
    lock_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "locks")
    os.makedirs(lock_dir, exist_ok=True)
    return os.path.join(lock_dir, re.sub(r"[^\w.-]", "_", network_name) + ".lock")


def _acquire(fd, network_name, timeout):
    if _try_lock(fd):
        return False
    logging.getLogger("BuildLock").info(f"Waiting for another schedule build of {network_name} to finish")
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        time.sleep(POLL_INTERVAL)
        if _try_lock(fd):
            return True
        if deadline is not None and time.monotonic() >= deadline:
            raise BuildLockTimeout(f"Gave up waiting for another schedule build of {network_name} after {timeout}s")


@contextlib.contextmanager
def station_build_lock(network_name, timeout=None):
    """
    Only one schedule build, reset or catalog rebuild per station at a time, across processes and threads.

    Yields True if another build had to finish first.
    """
    held = _held_by_this_thread()
    if network_name in held:
        yield False
        return

    fd = os.open(_lock_path(network_name), os.O_RDWR | os.O_CREAT)
    try:
        waited = _acquire(fd, network_name, timeout)
    except BaseException:
        os.close(fd)
        raise

    held.add(network_name)
    try:
        yield waited
    finally:
        held.discard(network_name)
        try:
            _unlock(fd)
        finally:
            os.close(fd)
