import sys
import os
import json
import datetime

sys.path.append(os.getcwd())
from fs42.station_manager import StationManager
from fs42.liquid_manager import LiquidManager
from fs42.liquid_blocks import LiquidBlock
from fs42.title_parser import TitleParser

def normalize_video_title(title):
    return TitleParser.parse_title(title)


class PreviewBlock:
    def __init__(self, title, width=1):
        self.title = title
        self.width = width
        self.started_earlier = False
        self.ends_later = False

    def __repr__(self):
        return f"{self.title}: width={self.width} started={self.started_earlier} later={self.ends_later}"

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__)


class ScheduleQuery:
    @staticmethod
    def query_slot(network_name, when, normalize):
        start_marker = when
        current_marker = start_marker
        next_marker = start_marker
        end_target = start_marker + datetime.timedelta(hours=1, minutes=30)
        blocks = []
        keep_going = True

        while keep_going:
            programming_block: LiquidBlock = LiquidManager().get_programming_block(network_name, current_marker)

            total_duration = programming_block.playback_duration()
            remaining_duration = datetime.timedelta(seconds=total_duration)
            started_earlier = False
            ends_later = False
            if programming_block.start_time < start_marker:
                remaining_duration = programming_block.end_time - start_marker
                started_earlier = True

            next_marker = current_marker + remaining_duration + datetime.timedelta(seconds=1)

            if next_marker > end_target:
                ends_later = True

            _display_title = normalize_video_title(programming_block.title) if normalize else programming_block.title

            _block = PreviewBlock(_display_title)
            _block.started_earlier = started_earlier
            _block.ends_later = ends_later
            _block.width = remaining_duration.total_seconds()
            blocks.append(_block)
            if next_marker > end_target:
                keep_going = False

            current_marker = next_marker

        return blocks


class GuideBuilder:
    def __init__(
        self, num_blocks=3, template_dir="fs42/guide_render/templates/", static_dir="fs42/guide_render/static/"
    ):
        # ordered array of {"conf": station_config, "schedule": schedule}
        self.num_blocks = num_blocks
        self.template_dir = template_dir
        self.static_dir = static_dir

    def build_view(self, normalize=True):
        view = {"rows": [], "meta": []}

        now = datetime.datetime.now()
        hour = now.hour

        if now.minute > 30:
            past_half = True
            start_time = now.replace(minute=30, second=1, microsecond=0)
        else:
            past_half = False
            start_time = now.replace(minute=0, second=1, microsecond=0)

        # each statio is a row
        for station in StationManager().stations:
            if station["network_type"] == "guide" or station["network_type"] == "streaming" or station["hidden"]:
                continue
            entries = ScheduleQuery.query_slot(station["network_name"], start_time, normalize)

            view["rows"].append(entries)
            network_name = station["network_name"]
            channel_number = station["channel_number"]
            view["meta"].append({"network_name": network_name, "channel_number": channel_number})

        timings = []
        hour_one = hour
        hour_two = hour + 1

        if hour_two >= 24:
            hour_two = 0

        # TODO: this isn't an extendable approach - only supports 3 time blocks
        if past_half:
            timings.append(f"{hour_one}:30")
            timings.append(f"{hour_two}:00")
            timings.append(f"{hour_two}:30")
        else:
            timings.append(f"{hour_one}:00")
            timings.append(f"{hour_one}:30")
            timings.append(f"{hour_two}:00")

        formatted_timings = []
        # TODO: Add configuration option for 24 vs 12 hour times
        for timing in timings:
            formatted = datetime.datetime.strptime(timing, "%H:%M").strftime("%I:%M %p")
            formatted_timings.append(formatted)

        view["timings"] = formatted_timings

        return view


if __name__ == "__main__":
    gb = GuideBuilder()
    blocks = gb.build_view()
    for block in blocks:
        print(block)
        print(blocks[block])
