import sys
import os
sys.path.append(os.getcwd())
from confs.fieldStation42_conf import main_conf
from fs42.timings import OPERATING_HOURS, DAYS
from fs42.show_block import ShowBlock, ClipBlock, MovieBlocks, ContinueBlock
from jinja2 import Environment, select_autoescape, FileSystemLoader
import json
import pickle
import datetime
import re
import math

def normalize_video_title(title):
    if "_V1" in title:
        (title, episode_id) = title.split("_V1")

    spaced = re.sub("[^a-zA-Z0-9]", " ", title)
    titled = spaced.title()
    return titled

class PreviewBlock:

    def __init__(self, title, width=1, continuation=False):
        self.title = title
        self.continuation = continuation
        self.width = width
        self.started_earlier = False
        self.ends_later = False
        self.is_back_half = False

    def __repr__(self):
        return f"{self.title}:{self.width}|{self.continuation}"

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class ScheduleQuery:

    def query_slot(schedule, day, hour):
        blocks = []
        for i in [0,1]:
            slot_key = hour + i
            if slot_key >= 24:
                slot_key = 0
            show = schedule[day][str(slot_key)]
            if isinstance(show, ShowBlock):
                title = normalize_video_title(show.front.title)
                if show.back:
                    blocks.append(PreviewBlock(title))
                    back_title = normalize_video_title(show.back.title)
                    back = PreviewBlock(back_title)
                    back.is_back_half = True
                    blocks.append(back)
                else:
                    #then it gets the whole hour
                    blocks.append(PreviewBlock(title, 2))

            elif isinstance(show, ClipBlock):
                title = normalize_video_title(show.title)
                blocks.append(PreviewBlock(title,2))
            elif isinstance(show, MovieBlocks):
                title = normalize_video_title(show.title)
                blocks.append(PreviewBlock(title, 4))
                break;
            elif isinstance(show, ContinueBlock):
                title = normalize_video_title(show.title)
                blocks.append(PreviewBlock(title, 2, True))

        return blocks


class GuideBuilder:
    def __init__(self, num_blocks=3, template_dir="fs42/guide_render/templates/", static_dir="fs42/guide_render/static/"):
        # ordered array of {"conf": station_config, "schedule": schedule}
        self.station_schedules = []
        self.num_blocks = num_blocks
        self.template_dir = template_dir
        self.static_dir = static_dir

    def build_view(self):
        slots = []
        view = {'rows': [], 'meta': []}

        now = datetime.datetime.now()
        week_day = DAYS[now.weekday()]
        hour = now.hour
        past_half = now.minute>30

        #stations are a row
        for station in self.station_schedules:

            entries = ScheduleQuery.query_slot(station['schedule'], week_day, hour)

            #is already past the half hour, remove one block from front
            if past_half:

                entries[0].width -= 1
                #only back halfs would not have started started_earlier

                if entries[0].width > 0:
                    entries[0].started_earlier


            #now trim the entries to only contain 3 blocks
            count = 0
            filtered = []
            for entry in entries:
                if count + entry.width <= self.num_blocks:
                    count += entry.width
                    filtered.append(entry)
                elif count < self.num_blocks:
                    entry.ends_later = True
                    entry.width = self.num_blocks-count
                    filtered.append(entry)
                    count = self.num_blocks
                if count >= self.num_blocks:
                    break

            view['rows'].append(filtered)
            network_name = station['conf']['network_name']
            channel_number = station['conf']['channel_number']
            view['meta'].append({"network_name": network_name, "channel_number": channel_number})
            print(view['meta'])

        timings = []
        hour_one = hour
        hour_two = hour+1


        if hour_two >= 24:
            hour_two = 0

        #TODO: this isn't an extendable approach - only supports 3 time blocks
        if past_half:
            timings.append(f"{hour_one}:30")
            timings.append(f"{hour_two}:00")
            timings.append(f"{hour_two}:30")
        else:
            timings.append(f"{hour_one}:00")
            timings.append(f"{hour_two}:30")
            timings.append(f"{hour_two}:00")

        formatted_timings = []
        #TODO: Add configuration option for 24 vs 12 hour times
        for timing in timings:
            formatted = datetime.datetime.strptime(timing, "%H:%M").strftime("%I:%M %p")
            formatted_timings.append(formatted)

        view["timings"] = formatted_timings

        return view

    def render(self, render_template="90s_template.html", output="90s.html"):
        view = self.build_view()
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape( enabled_extensions=('html', 'xml'), default_for_string=True,)
        )

        template = env.get_template(render_template)
        rendered = template.render(view=view)
        with open(f"{self.static_dir}/{output}", "w") as fp:
            fp.write(rendered)

    def load_schedules(self, station_configs):
        for station_config in station_configs:
            if 'network_type' in station_config and station_config['network_type'] == "guide":
                pass
            else:
                with open(station_config['schedule_path'], "rb") as f:
                    full_schedule  = pickle.load(f)
                    #print(full_schedule)
                    self.station_schedules.append({"conf": station_config, "schedule": full_schedule})


if __name__ == "__main__":
    gb = GuideBuilder()
    gb.load_schedules(main_conf['stations'])
    gb.render()

