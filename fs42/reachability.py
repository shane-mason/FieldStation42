"""Reachability monitor for web and streaming channels.

Web (``web_url``) and streaming (``streams[*].url``) stations depend on remote
hosts. This module runs a small daemon thread that periodically TCP-connects to
those hosts so the player, native guide and 4242 server can treat unreachable
stations as offline (hide them from channel up/down, hide them from the native
guide, badge them in the web UI).

Design notes:
- One monitor per *process*. The player, the forked guide channel process and
  the FastAPI server process each get their own. ``get_monitor()`` restarts the
  thread when it finds one that is not alive - a forked child inherits the
  parent's borg dict but not its threads.
- Probing is concurrent and de-duplicated by host:port so a cycle is bounded by
  roughly one ``reachability_timeout`` regardless of how many stations/URLs are
  configured. This matters most when the uplink is down and every probe fails.
- A station whose reachability has not been checked yet is reported as
  reachable (optimistic) so nothing flickers at startup.
"""

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlparse

PROBE_TYPES = ("web", "streaming")

DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "rtsp": 554,
    "rtsps": 322,
    "rtmp": 1935,
    "rtmps": 443,
    "mms": 1755,
    "udp": None,
    "rtp": None,
}

_MONITOR_KEY = "_reachability_monitor"
_MAX_PROBE_WORKERS = 8


def probe_urls_for(station):
    """Return the list of remote URLs a station depends on (may be empty)."""
    ntype = station.get("network_type")
    if ntype == "web":
        url = station.get("web_url")
        return [url] if url else []
    if ntype == "streaming":
        return [s.get("url") for s in (station.get("streams") or []) if isinstance(s, dict) and s.get("url")]
    return []


def probe_target_for(url):
    """Map a URL to a (host, port) TCP target, or None if it can't be probed."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = parsed.hostname
    if not host:
        return None
    scheme = (parsed.scheme or "http").lower()
    if scheme in DEFAULT_PORTS and DEFAULT_PORTS[scheme] is None:
        return None
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = DEFAULT_PORTS.get(scheme, 80)
    return (host, port)


def tcp_probe(target, timeout):
    host, port = target
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:
        return False


class ReachabilityMonitor:
    def __init__(self, interval=30, timeout=5, name_prefix="ReachabilityMonitor"):
        self.interval = max(1, int(interval))
        self.timeout = max(0.5, float(timeout))
        self._l = logging.getLogger("REACHABILITY")
        self._lock = threading.Lock()
        self._status = {}
        self._first_check_done = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._name_prefix = name_prefix


    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self._name_prefix, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def wait_first_check(self, timeout=None):
        """Block until the first probe cycle completes (or timeout). Returns True if done."""
        return self._first_check_done.wait(timeout)


    def is_reachable(self, network_name):
        with self._lock:
            return self._status.get(network_name, True)

    def snapshot(self):
        with self._lock:
            return dict(self._status)


    def _run(self):
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.check_once()
            except Exception as e:
                self._l.exception(f"Reachability check failed: {e}")
            self._first_check_done.set()
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.0, self.interval - elapsed))

    def check_once(self, stations=None):
        """Run one probe cycle. Returns the new {network_name: reachable} map."""
        if stations is None:
            from fs42.station_manager import StationManager

            stations = StationManager().stations

        plan = {}
        targets = set()
        for station in stations:
            if station.get("network_type") not in PROBE_TYPES:
                continue
            name = station.get("network_name")
            if station.get("always_available", False):
                plan[name] = None
                continue
            station_targets = []
            for url in probe_urls_for(station):
                t = probe_target_for(url)
                if t is not None:
                    station_targets.append(t)
                    targets.add(t)
            plan[name] = station_targets

        results = self._probe_targets(targets)

        new_status = {}
        for name, station_targets in plan.items():
            if station_targets is None or len(station_targets) == 0:
                new_status[name] = True
            else:
                new_status[name] = any(results.get(t, False) for t in station_targets)

        with self._lock:
            for name, reachable in new_status.items():
                prev = self._status.get(name)
                if prev is not None and prev != reachable:
                    self._l.info(f"Channel '{name}' is now {'ONLINE' if reachable else 'OFFLINE'}")
                elif prev is None and not reachable:
                    self._l.warning(f"Channel '{name}' is OFFLINE (unreachable)")
            self._status = new_status
        return new_status

    def _probe_targets(self, targets):
        if not targets:
            return {}
        targets = list(targets)
        results = {}
        workers = min(_MAX_PROBE_WORKERS, len(targets))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fs42-probe")
        try:
            futures = {pool.submit(tcp_probe, t, self.timeout): t for t in targets}
            batches = -(-len(targets) // workers)
            done, _ = wait(futures, timeout=self.timeout * batches + 1.0)
            for fut in done:
                try:
                    results[futures[fut]] = bool(fut.result())
                except Exception:
                    results[futures[fut]] = False
            for t in targets:
                results.setdefault(t, False)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return results


def get_monitor():
    """Return the per-process monitor, starting (or restarting after fork) as needed."""
    from fs42.station_manager import StationManager

    manager = StationManager()
    conf = manager.server_conf
    monitor = manager.__dict__.get(_MONITOR_KEY)
    if monitor is None or not monitor.is_alive():
        if monitor is not None:
            fresh = ReachabilityMonitor(
                interval=conf.get("reachability_interval", 30),
                timeout=conf.get("reachability_timeout", 5),
            )
            fresh._status = monitor.snapshot()
            monitor = fresh
        else:
            monitor = ReachabilityMonitor(
                interval=conf.get("reachability_interval", 30),
                timeout=conf.get("reachability_timeout", 5),
            )
        monitor.start()
        manager.__dict__[_MONITOR_KEY] = monitor
    return monitor
