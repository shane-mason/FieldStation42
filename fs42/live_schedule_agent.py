import datetime
import logging
import multiprocessing
import signal
import time
from queue import Empty

REQUEST_COOLDOWN = 10 * 60
FIRST_PLAY_FALLBACK = 60
CHECK_INTERVAL = 60 * 60
PRUNE_AGE = datetime.timedelta(hours=48)
REQUESTED_MAX_DAYS = 3
BUILD_LOCK_TIMEOUT = 15 * 60

TRIGGER_DELTAS = {
    "day": datetime.timedelta(days=1),
    "week": datetime.timedelta(weeks=1),
    "month": datetime.timedelta(days=30),
}


class LiveScheduleAgent:
    """Player side handle for the schedule agent process. Every call is fire and forget."""

    def __init__(self, schedule_agent_conf=None):
        self._queue = multiprocessing.Queue()
        self._first_play_sent = False
        self._process = multiprocessing.Process(
            target=run_schedule_agent,
            args=(self._queue, schedule_agent_conf),
            daemon=True,
        )
        self._process.start()

    def request_build(self, network_name):
        self._queue.put(("build", network_name, time.monotonic()))

    def first_play(self):
        if not self._first_play_sent:
            self._first_play_sent = True
            self._queue.put(("first_play",))

    def stop(self):
        self._queue.put(("stop",))


def run_schedule_agent(queue, schedule_agent_conf):
    # the player owns shutdown - it terminates this process on exit
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ScheduleAgentWorker(schedule_agent_conf).run(queue)


class ScheduleAgentWorker:

    def __init__(self, schedule_agent_conf=None, clock=time.monotonic):
        self._l = logging.getLogger("ScheduleAgent")
        self._clock = clock
        self._topup_amount = None
        self._trigger_at = None
        self._trigger_delta = None
        if schedule_agent_conf:
            self._topup_amount = schedule_agent_conf["amount_to_add"]
            self._trigger_at = schedule_agent_conf["trigger_add_at"]
            self._trigger_delta = TRIGGER_DELTAS[self._trigger_at]
        self._started = clock()
        self._first_play = False
        self._last_check = None
        self._requested = []
        self._topups = []
        self._last_build = {}
        self._warned = set()
        self._stopped = False

    def run(self, queue):
        if self._topup_amount:
            self._l.info(f"Schedule agent started - top-ups add a {self._topup_amount} when a schedule is within a {self._trigger_at} of ending")
        else:
            self._l.info("Schedule agent started - top-ups not configured, schedules are only built when a channel runs out")
        while not self._stopped:
            self._drain(queue)
            if self._stopped:
                break
            if self.has_work():
                self.step()
            else:
                try:
                    self.handle_message(queue.get(timeout=1))
                except Empty:
                    pass
        self._l.info("Schedule agent stopped")

    def _drain(self, queue):
        while True:
            try:
                self.handle_message(queue.get_nowait())
            except Empty:
                return

    def handle_message(self, message):
        match message[0]:
            case "build":
                self._request(message[1], message[2])
            case "first_play":
                self._first_play = True
            case "stop":
                self._stopped = True

    def _request(self, network_name, sent_at):
        if network_name in self._requested:
            return
        finished = self._last_build.get(network_name)
        if finished is not None:
            if sent_at < finished:
                # sent while that build was still running
                return
            if self._clock() - finished < REQUEST_COOLDOWN:
                if network_name not in self._warned:
                    self._warned.add(network_name)
                    self._l.error(
                        f"Built a schedule for {network_name} but it still has nothing to play - "
                        f"will try again in {REQUEST_COOLDOWN // 60} minutes"
                    )
                return
        self._requested.append(network_name)

    def _topups_unlocked(self):
        return self._first_play or self._clock() - self._started >= FIRST_PLAY_FALLBACK

    def _check_due(self):
        if not self._topups_unlocked():
            return False
        return self._last_check is None or self._clock() - self._last_check >= CHECK_INTERVAL

    def has_work(self):
        return bool(self._requested or self._topups or self._check_due())

    def step(self):
        if self._requested:
            self._build_requested(self._requested.pop(0))
        elif self._topups:
            self._build_topup(self._topups.pop(0))
        elif self._check_due():
            self._last_check = self._clock()
            self.prune()
            if self._topup_amount:
                self._topups = self.stations_needing_topup()

    def _build_requested(self, network_name):
        station = self.lookup_station(network_name)
        if not station or not station.get("_has_schedule", False):
            return
        self.prune()
        self._l.info(f"Building schedule for {network_name} - requested by the player")
        try:
            self.build_until_now(station)
            self._l.info(f"Finished building schedule for {network_name}")
        except Exception as e:
            self._l.error(f"Failed to build schedule for {network_name}: {e}")
        finally:
            self._last_build[network_name] = self._clock()
            self._warned.discard(network_name)

    def _build_topup(self, station):
        network_name = station["network_name"]
        self._l.info(f"Topping up schedule for {network_name} by a {self._topup_amount}")
        try:
            self.build_amount(station, self._topup_amount)
            self._l.info(f"Finished topping up schedule for {network_name}")
        except Exception as e:
            self._l.error(f"Failed to top up schedule for {network_name}: {e}")

    def lookup_station(self, network_name):
        from fs42.station_manager import StationManager

        return StationManager().station_by_name(network_name)

    def build_until_now(self, station):
        from fs42.build_lock import station_build_lock
        from fs42.liquid_api import LiquidAPI
        from fs42.liquid_schedule import LiquidSchedule

        with station_build_lock(station["network_name"], timeout=BUILD_LOCK_TIMEOUT):
            schedule = None
            target = datetime.datetime.now() + datetime.timedelta(hours=1)
            for _ in range(REQUESTED_MAX_DAYS):
                (_, end) = LiquidAPI.get_extents(station)
                if end is not None and end > target:
                    if schedule is None:
                        self._l.info(f"{station['network_name']} was built by another build while we waited")
                    return
                schedule = schedule or LiquidSchedule(station)
                schedule.add_days(1)

    def build_amount(self, station, amount):
        from fs42.build_lock import station_build_lock
        from fs42.liquid_api import LiquidAPI
        from fs42.liquid_schedule import LiquidSchedule

        with station_build_lock(station["network_name"], timeout=BUILD_LOCK_TIMEOUT):
            (_, end) = LiquidAPI.get_extents(station)
            if end is not None and end >= datetime.datetime.now() + self._trigger_delta:
                self._l.info(f"{station['network_name']} was topped up by another build while we waited")
                return
            LiquidSchedule(station).add_amount(amount)

    def stations_needing_topup(self):
        from fs42.liquid_api import LiquidAPI
        from fs42.station_manager import StationManager

        threshold = datetime.datetime.now() + self._trigger_delta
        needs_build = []
        for station in StationManager().stations:
            if not station.get("_has_schedule", False):
                continue
            (_, end) = LiquidAPI.get_extents(station)
            if end is None or end < threshold:
                self._l.info(f"{station['network_name']} schedule ends at {end}, threshold is {threshold} - needs top-up")
                needs_build.append(station)
        return needs_build

    def prune(self):
        from fs42.liquid_api import LiquidAPI

        cutoff = datetime.datetime.now() - PRUNE_AGE
        try:
            removed = LiquidAPI.prune_blocks(cutoff)
            if removed:
                self._l.info(f"Pruned {removed} schedule block(s) that ended before {cutoff}")
        except Exception as e:
            self._l.error(f"Failed to prune old schedule blocks: {e}")
