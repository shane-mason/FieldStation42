import logging
import random
from fs42.schedule_hint import hint_klass_matcher

class MarathonAgent:
    _l = logging.getLogger("MARATHONAGENT")

    @staticmethod
    def detect_marathon(slot: dict, when):
        if "marathon" in slot and "count" in slot["marathon"]:
            marathon = slot["marathon"]
        else:
            return False

        if "chance" in marathon:
            #check if there is a date hint
            if "hint" in marathon:
                hint_str = marathon["hint"]
                hint_klass = hint_klass_matcher(hint_str)
                if hint_klass:
                    hint_instance = hint_klass(hint_str)
                    if not hint_instance.hint(when):
                        # there was a hint, but the time doesn't fit
                        return False
                else:
                    MarathonAgent._l.warning(
                        f"Marathon hint '{hint_str}' doesn't match any hint type "
                        "and will be ignored - this marathon is unrestricted"
                    )

            if random.random() < marathon["chance"]:
                return True


        return False

    @staticmethod
    def fill_marathon(slot: dict):
        follow_on = {key: value for key, value in slot.items() if key != "marathon"}
        return [follow_on] * (slot["marathon"]["count"] - 1)
