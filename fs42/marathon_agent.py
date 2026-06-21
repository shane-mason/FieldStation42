import random
from fs42.schedule_hint import hint_klass_matcher

class MarathonAgent:
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

            if random.random() < marathon["chance"]:
                return True


        return False

    @staticmethod
    def fill_marathon(slot: dict):
        buffer = []
        count = slot["marathon"]["count"]
        del slot["marathon"]
        for _ in range(count - 1):
            buffer.append(slot)
        return buffer
