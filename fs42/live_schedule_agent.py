import multiprocessing
import datetime
import logging


def _worker_build_schedules(lock, stations_to_build, amount_to_add):
    _l = logging.getLogger("ScheduleAgent.Worker")
    _l.info(f"Worker started - building {amount_to_add} for {len(stations_to_build)} station(s)")

    # import here to avoid issues with multiprocessing and module state
    from fs42.liquid_schedule import LiquidSchedule

    for station_conf in stations_to_build:
        name = station_conf["network_name"]
        try:
            _l.info(f"Building {amount_to_add} of schedule for {name}")
            with lock:
                schedule = LiquidSchedule(station_conf)
                schedule.add_amount(amount_to_add)
            _l.info(f"Finished building schedule for {name}")
        except Exception as e:
            _l.error(f"Failed to build schedule for {name}: {e}")

    _l.info("Worker finished")


class LiveScheduleAgent:
    # map config strings to timedeltas for the trigger threshold
    _trigger_deltas = {
        "day": datetime.timedelta(days=1),
        "week": datetime.timedelta(weeks=1),
        "month": datetime.timedelta(days=30),
    }

    def __init__(self, schedule_agent_conf, lock):
        self._l = logging.getLogger("ScheduleAgent")
        self._lock = lock
        self._amount_to_add = schedule_agent_conf["amount_to_add"]
        self._trigger_at = schedule_agent_conf["trigger_add_at"]
        self._trigger_delta = self._trigger_deltas[self._trigger_at]
        self._worker = None
        self._last_check = None
        self._check_interval = datetime.timedelta(hours=1)
        self._l.info(
            f"Live schedule agent initialized: "
            f"trigger_at={self._trigger_at}, amount_to_add={self._amount_to_add}"
        )

    def get_lock(self):
        return self._lock

    def _needs_check(self):
        now = datetime.datetime.now()
        if self._last_check is None:
            self._last_check = now
            return True
        if now - self._last_check >= self._check_interval:
            self._last_check = now
            return True
        return False

    def _find_stations_needing_schedules(self):
        from fs42.liquid_manager import LiquidManager
        from fs42.station_manager import StationManager

        liquid = LiquidManager()
        now = datetime.datetime.now()
        threshold = now + self._trigger_delta
        needs_build = []

        for station in StationManager().stations:
            if not station.get("_has_schedule", False):
                continue
            name = station["network_name"]
            try:
                (start, end) = liquid.get_extents(name)
                if end is None or end < threshold:
                    self._l.info(
                        f"{name} schedule ends at {end}, threshold is {threshold} - needs build"
                    )
                    needs_build.append(station)
            except ValueError:
                continue

        return needs_build

    def _worker_finished(self):
        if self._worker is None:
            return False
        if self._worker.is_alive():
            return False

        exitcode = self._worker.exitcode
        if exitcode != 0:
            self._l.warning(f"Schedule build worker exited with code {exitcode}")
        else:
            self._l.info("Schedule build worker completed successfully")

        self._worker = None
        return True

    def tick(self):
        # first, check if a previous worker finished
        if self._worker_finished():
            from fs42.liquid_manager import LiquidManager

            self._l.info("Reloading schedules after background build")
            LiquidManager().reload_schedules()
            return True

        # don't spawn a new worker if one is running
        if self._worker is not None:
            return False

        # only check periodically
        if not self._needs_check():
            return False

        stations = self._find_stations_needing_schedules()
        if not stations:
            return False

        self._l.info(f"Spawning worker to build schedules for {len(stations)} station(s)")
        self._worker = multiprocessing.Process(
            target=_worker_build_schedules,
            args=(self._lock, stations, self._amount_to_add),
            daemon=True,
        )
        self._worker.start()
        return False