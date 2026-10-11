import datetime

from fs42.config_processor import ConfigProcessor
from fs42.marathon_agent import MarathonAgent
from fs42.slot_reader import SlotReader

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONDAY_8PM = datetime.datetime(2026, 10, 12, 20, 0)


def _conf():
    return ConfigProcessor.preprocess({
        "network_name": "T",
        "day_templates": {"d": {"20": {"tags": "drama", "marathon": {"chance": 1.0, "count": 3}}}},
        **{day: "d" for day in DAYS},
    })


def test_marathon_can_trigger_every_week_in_one_run():
    conf = _conf()
    for week in range(3):
        when = MONDAY_8PM + datetime.timedelta(weeks=week)
        slot, _ = SlotReader.get_slot(conf, when)
        assert MarathonAgent.detect_marathon(slot, when)
        MarathonAgent.fill_marathon(slot)


def test_fill_leaves_the_slot_untouched():
    conf = _conf()
    slot, _ = SlotReader.get_slot(conf, MONDAY_8PM)
    MarathonAgent.fill_marathon(slot)
    assert slot == {"tags": "drama", "marathon": {"chance": 1.0, "count": 3}}


def test_follow_on_hours_repeat_the_slot_without_retriggering():
    slot = {"tags": "drama", "start_bump": "intro", "marathon": {"chance": 1.0, "count": 3}}
    buffer = MarathonAgent.fill_marathon(slot)
    assert buffer == [{"tags": "drama", "start_bump": "intro"}] * 2
    assert not any(MarathonAgent.detect_marathon(s, MONDAY_8PM) for s in buffer)
