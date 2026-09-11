import socket
import threading
from unittest.mock import patch

import pytest

from fs42.station_manager import StationManager
from fs42.station_io import StationIO
from fs42 import reachability
from fs42.reachability import (
    ReachabilityMonitor,
    probe_target_for,
    probe_urls_for,
    get_monitor,
)


def _reset_manager(server_conf_overrides=None):
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    config_data = {"server_port": 4242}
    if server_conf_overrides:
        config_data.update(server_conf_overrides)
    with patch.object(StationIO, "load_main_config", return_value=config_data):
        with patch("fs42.station_io.glob.glob", return_value=[]):
            return StationManager()


def _station(name, ntype, **extra):
    d = {"network_name": name, "network_type": ntype, "channel_number": 1, "hidden": False}
    d.update(extra)
    return d



class TestProbeUrls:
    def test_web_uses_web_url(self):
        assert probe_urls_for(_station("w", "web", web_url="https://example.com/x")) == ["https://example.com/x"]

    def test_web_without_url_is_empty(self):
        assert probe_urls_for(_station("w", "web")) == []

    def test_streaming_collects_all_stream_urls(self):
        st = _station("s", "streaming", streams=[
            {"url": "https://a.example/1.m3u8", "duration": 30, "title": "a"},
            {"url": "rtsp://b.example/live", "duration": 30, "title": "b"},
            {"duration": 30, "title": "no url"},
        ])
        assert probe_urls_for(st) == ["https://a.example/1.m3u8", "rtsp://b.example/live"]

    def test_streaming_without_streams_is_empty(self):
        assert probe_urls_for(_station("s", "streaming")) == []
        assert probe_urls_for(_station("s", "streaming", streams=[])) == []

    @pytest.mark.parametrize("ntype", ["standard", "loop", "guide", "executable"])
    def test_other_types_have_nothing_to_probe(self, ntype):
        assert probe_urls_for(_station("x", ntype, web_url="https://example.com")) == []


class TestProbeTarget:
    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/a.m3u8", ("example.com", 443)),
        ("http://example.com/a", ("example.com", 80)),
        ("http://example.com:8080/a", ("example.com", 8080)),
        ("rtsp://cam.local/live", ("cam.local", 554)),
        ("rtmp://cdn.example/app", ("cdn.example", 1935)),
        ("udp://239.0.0.1:1234", None),
        ("not a url", None),
        ("", None),
    ])
    def test_targets(self, url, expected):
        assert probe_target_for(url) == expected



class TestMonitorCheckOnce:
    def _probe_map(self, up_hosts):
        def fake(target, timeout):
            return target[0] in up_hosts
        return fake

    def test_unknown_is_optimistic(self):
        m = ReachabilityMonitor()
        assert m.is_reachable("nope") is True

    def test_web_offline_when_host_down(self):
        m = ReachabilityMonitor()
        stations = [_station("w", "web", web_url="https://down.example/")]
        with patch.object(reachability, "tcp_probe", self._probe_map(set())):
            status = m.check_once(stations)
        assert status == {"w": False}
        assert m.is_reachable("w") is False

    def test_web_online_when_host_up(self):
        m = ReachabilityMonitor()
        stations = [_station("w", "web", web_url="https://up.example/")]
        with patch.object(reachability, "tcp_probe", self._probe_map({"up.example"})):
            assert m.check_once(stations) == {"w": True}

    def test_streaming_reachable_if_any_stream_up(self):
        m = ReachabilityMonitor()
        st = _station("s", "streaming", streams=[
            {"url": "https://down1.example/a"},
            {"url": "https://up.example/b"},
            {"url": "https://down2.example/c"},
        ])
        with patch.object(reachability, "tcp_probe", self._probe_map({"up.example"})):
            assert m.check_once([st]) == {"s": True}

    def test_streaming_offline_if_all_streams_down(self):
        m = ReachabilityMonitor()
        st = _station("s", "streaming", streams=[{"url": "https://d1.example/a"}, {"url": "https://d2.example/b"}])
        with patch.object(reachability, "tcp_probe", self._probe_map(set())):
            assert m.check_once([st]) == {"s": False}

    def test_always_available_skips_probe_and_is_reachable(self):
        m = ReachabilityMonitor()
        st = _station("diag", "web", web_url="http://localhost:4242/static/diagnostics.html", always_available=True)
        calls = []

        def fake(target, timeout):
            calls.append(target)
            return False

        with patch.object(reachability, "tcp_probe", fake):
            assert m.check_once([st]) == {"diag": True}
        assert calls == []

    def test_no_urls_is_reachable(self):
        m = ReachabilityMonitor()
        with patch.object(reachability, "tcp_probe", self._probe_map(set())):
            assert m.check_once([_station("w", "web"), _station("s", "streaming", streams=[])]) == {"w": True, "s": True}

    def test_non_remote_types_not_tracked(self):
        m = ReachabilityMonitor()
        with patch.object(reachability, "tcp_probe", self._probe_map(set())):
            assert m.check_once([_station("std", "standard"), _station("g", "guide")]) == {}
        assert m.is_reachable("std") is True

    def test_targets_are_deduplicated_across_stations(self):
        m = ReachabilityMonitor()
        seen = []

        def fake(target, timeout):
            seen.append(target)
            return True

        stations = [
            _station("a", "web", web_url="https://same.example/a"),
            _station("b", "web", web_url="https://same.example/b"),
            _station("c", "streaming", streams=[{"url": "https://same.example/c.m3u8"}]),
        ]
        with patch.object(reachability, "tcp_probe", fake):
            m.check_once(stations)
        assert seen == [("same.example", 443)]

    def test_real_tcp_probe_against_local_listener(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            m = ReachabilityMonitor(timeout=1)
            up = _station("up", "web", web_url=f"http://127.0.0.1:{port}/")
            assert m.check_once([up]) == {"up": True}
        finally:
            srv.close()
        m2 = ReachabilityMonitor(timeout=1)
        assert m2.check_once([up]) == {"up": False}


class TestMonitorThread:
    def test_start_runs_first_check_and_sets_event(self):
        m = ReachabilityMonitor(interval=60, timeout=1)
        st = _station("w", "web", web_url="https://x.example/")
        manager = _reset_manager()
        manager.stations = [st]
        with patch.object(reachability, "tcp_probe", lambda t, to: False):
            m.start()
            assert m.wait_first_check(timeout=5)
            assert m.is_reachable("w") is False
            m.stop()


class TestGetMonitor:
    def test_get_monitor_is_per_process_singleton(self):
        manager = _reset_manager()
        manager.stations = []
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2
        assert m1.is_alive()
        m1.stop()

    def test_get_monitor_restarts_dead_thread_and_keeps_status(self):
        manager = _reset_manager()
        st = _station("w", "web", web_url="https://down.example/")
        manager.stations = [st]
        dead = ReachabilityMonitor()
        dead._status = {"w": False}
        dead._thread = threading.Thread(target=lambda: None)
        dead._thread.start()
        dead._thread.join()
        manager.__dict__[reachability._MONITOR_KEY] = dead
        with patch.object(reachability, "tcp_probe", lambda t, to: False):
            fresh = get_monitor()
            assert fresh is not dead
            assert fresh.is_alive()
            assert fresh.is_reachable("w") is False
            assert fresh.wait_first_check(timeout=5)
            assert fresh.is_reachable("w") is False
            assert manager.is_hidden(st) is True
            fresh.stop()

    def test_get_monitor_uses_server_conf(self):
        manager = _reset_manager({"reachability_interval": 7, "reachability_timeout": 2})
        manager.stations = []
        m = get_monitor()
        assert m.interval == 7
        assert m.timeout == 2
        m.stop()



class TestStationManagerVisibility:
    def test_defaults_loaded(self):
        manager = _reset_manager()
        assert manager.server_conf["reachability_check"] is True
        assert manager.server_conf["reachability_interval"] == 30
        assert manager.server_conf["reachability_timeout"] == 5

    def test_main_config_overrides(self):
        manager = _reset_manager({"reachability_check": False, "reachability_interval": 10})
        assert manager.server_conf["reachability_check"] is False
        assert manager.server_conf["reachability_interval"] == 10

    def test_offline_web_station_is_hidden(self):
        manager = _reset_manager()
        st = _station("w", "web", web_url="https://down.example/")
        manager.stations = [st]
        m = get_monitor()
        with patch.object(reachability, "tcp_probe", lambda t, to: False):
            m.check_once([st])
        assert manager.is_channel_offline(st) is True
        assert manager.is_hidden(st) is True
        m.stop()

    def test_config_hidden_still_hidden_when_online(self):
        manager = _reset_manager()
        st = _station("w", "web", web_url="https://up.example/", hidden=True)
        manager.stations = [st]
        m = get_monitor()
        with patch.object(reachability, "tcp_probe", lambda t, to: True):
            m.check_once([st])
        assert manager.is_channel_offline(st) is False
        assert manager.is_hidden(st) is True
        m.stop()

    def test_always_available_never_offline(self):
        manager = _reset_manager()
        st = _station("diag", "web", web_url="http://localhost:1/", always_available=True)
        manager.stations = [st]
        m = get_monitor()
        with patch.object(reachability, "tcp_probe", lambda t, to: False):
            m.check_once([st])
        assert manager.is_channel_offline(st) is False
        assert manager.is_hidden(st) is False
        m.stop()

    def test_reachability_check_disabled_never_offline(self):
        manager = _reset_manager({"reachability_check": False})
        st = _station("w", "web", web_url="https://down.example/")
        manager.stations = [st]
        assert manager.is_channel_offline(st) is False
        assert manager.is_hidden(st) is False
        assert reachability._MONITOR_KEY not in manager.__dict__

    def test_standard_station_never_offline(self):
        manager = _reset_manager()
        st = _station("std", "standard")
        manager.stations = [st]
        assert manager.is_channel_offline(st) is False
        assert reachability._MONITOR_KEY not in manager.__dict__
