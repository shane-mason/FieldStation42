import datetime
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42.liquid_schedule import LiquidSchedule  # noqa: E402


def _schedule(offset, existing_end):
    schedule = LiquidSchedule.__new__(LiquidSchedule)
    schedule.conf = {"network_type": "standard", "schedule_offset": offset}
    schedule._end_time = lambda: existing_end
    schedule.built = []
    schedule._fluid = lambda start, end: schedule.built.append((start, end))
    return schedule


def test_first_build_starts_at_midnight_plus_offset():
    schedule = _schedule(20, None)
    schedule._increment("day")
    midnight = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    assert schedule.built[0][0] == midnight + datetime.timedelta(minutes=20)


def test_continuing_build_starts_where_the_schedule_ends():
    existing_end = datetime.datetime(2026, 10, 11, 0, 20)
    schedule = _schedule(20, existing_end)
    schedule._increment("day")
    assert schedule.built[0][0] == existing_end


def test_repeated_builds_leave_no_gaps():
    end = None
    for _ in range(3):
        schedule = _schedule(20, end)
        schedule._increment("day")
        start, target_end = schedule.built[0]
        if end is not None:
            assert start == end
        end = target_end
