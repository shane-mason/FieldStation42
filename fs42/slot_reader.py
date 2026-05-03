from datetime import datetime
import copy
import random
import math

from fs42 import timings


class SlotReader:
    @staticmethod
    def get_tag(conf, when: datetime):
        response = None
        slot = SlotReader.get_slot(conf, when)
        if slot and "tags" in slot:
            tags = slot["tags"]

            if type(tags) is list:
                if len(tags) == 1 or when.minute < 30:
                    response = tags[0]
                else:
                    response = tags[1]
            else:
                response = tags

        return response

    def get_tag_from_slot(slot, when: datetime):
        response = None
        if slot and "tags" in slot:
            tags = slot["tags"]

            is_random = False

            if "random_tags" in slot and slot["random_tags"]:
                is_random = True

            if type(tags) is list:
                if is_random:
                    response = random.choice(tags)
                else:
                    # first, figure out what our segments are
                    num_tags = len(tags)
                    # get the duration of the segmentations in minutes
                    segment_duration = math.floor(60/num_tags)
                    # figure out what segment we are in
                    current_segment = math.floor(when.minute/segment_duration)
                    # make sure its not too long
                    if current_segment >= num_tags:
                        current_segment = num_tags-1

                    return tags[current_segment]
            else:
                response = tags

        return response

    @staticmethod
    def _date_key_matches(date_key, when: datetime):
        # match date_overrides keys like "April 23" or "December 24 - January 2"
        try:
            parts = [part.strip() for part in date_key.split(" - ")]

            if len(parts) == 1:
                parsed = datetime.strptime(parts[0], "%B %d")
                return parsed.month == when.month and parsed.day == when.day

            if len(parts) == 2:
                start = datetime.strptime(parts[0], "%B %d")
                end = datetime.strptime(parts[1], "%B %d")

                current_md = (when.month, when.day)
                start_md = (start.month, start.day)
                end_md = (end.month, end.day)

                # normal same-year range, e.g. "April 23 - April 25"
                if start_md <= end_md:
                    return start_md <= current_md <= end_md

                # wraparound range, e.g. "December 24 - January 2"
                return current_md >= start_md or current_md <= end_md

            return False
        except ValueError:
            return False

    @staticmethod
    def _get_date_override(conf, when: datetime):
        overrides = conf.get("date_overrides", {})

        if not isinstance(overrides, dict):
            return None

        for date_key, override_conf in overrides.items():
            if SlotReader._date_key_matches(date_key, when):
                return override_conf

        return None

    def get_slot(conf, when: datetime):
        slot_number = str(when.hour)
        # check for exact date override first, then fall back to weekday schedule
        date_override = SlotReader._get_date_override(conf, when)
        if date_override and slot_number in date_override:
            return date_override[slot_number]

        day_str = timings.DAYS[when.weekday()]
        response = None
        if day_str in conf:
            if slot_number in conf[day_str]:
                response = conf[day_str][slot_number]

        return response

    @staticmethod
    def smooth_tags(conf):
        # this function smooths tags through slot boundaries - so if not specified will use previous slots tag.
        last_tag = None
        smoothed = copy.deepcopy(conf)
        for day_index in timings.DAYS:
            for slot_index in timings.OPERATING_HOURS:
                slot_index = str(slot_index)
                if slot_index in conf[day_index]:
                    if "tags" in conf[day_index][slot_index]:
                        last_tag = conf[day_index][slot_index]
                    elif "continued" in conf[day_index][slot_index]:
                        if conf[day_index][slot_index]["continued"]:
                            smoothed[day_index][slot_index]["tags"] = last_tag["tags"]
        return smoothed
