import random


class MarathonAgent:
    @staticmethod
    def detect_marathon(slot: dict):
        if "marathon" in slot and "count" in slot["marathon"]:
            marathon = slot["marathon"]
            if "chance" in marathon:
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
