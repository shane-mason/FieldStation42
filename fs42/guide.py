import sys
sys.path.insert(0, 'confs')

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
                    blocks.append(PreviewBlock(title))
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

    def __init__(self):
        # ordered array of {"conf": station_config, "schedule": schedule}
        self.station_schedules = []


    def build_view(self, station_name="", station_number=""):
        slots = []
        view = {'rows': []}

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
            #now trim the entries to only contain 3 blocks
            count = 0
            filtered = []
            for entry in entries:
                if count + entry.width <= 3:
                    count += entry.width
                    filtered.append(entry)
                elif count < 3:
                    entry.width = 3-count
                    filtered.append(entry)
                    count = 3
                if count >= 3:
                    break
            print(filtered)
            view['rows'].append(filtered)

        return view

    def render(self):
        view = self.build_view()
        env = Environment(
            loader=FileSystemLoader("guide/"),
            autoescape=select_autoescape( enabled_extensions=('html', 'xml'),default_for_string=True,)
            )

        template = env.get_template("test.html")
        rendered = template.render(view=view)
        with open("rendered.html", "w") as fp:
            fp.write(rendered)

    def load_schedules(self, station_configs):
        for station_config in station_configs:
            with open(station_config['schedule_path'], "rb") as f:
                full_schedule  = pickle.load(f)
                #print(full_schedule)
                self.station_schedules.append({"conf": station_config, "schedule": full_schedule})


import sys
from PySide6.QtWidgets import (QLineEdit, QPushButton, QApplication,
    QVBoxLayout, QDialog, QWidget, QMainWindow)
from PySide6.QtWebEngineWidgets import QWebEngineView

# requires: apt-get install libnss3

#QWebEngineView *view = new QWebEngineView(parent);
#view->load(QUrl("http://www.qt.io/"));
#view->show();

class Form(QWidget):

    def __init__(self, parent=None):
        super(Form, self).__init__(parent)
        # Create widgets
        self.view = QWebEngineView(self)
        self.view.load("file:////home/wrongdog/FieldStation42/rendered.html")


        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.view)
        # Set dialog layout
        self.setLayout(layout)
        self.resize(720, 480)


if __name__ == "__main__":
    gb = GuideBuilder()
    gb.load_schedules(main_conf['stations'])
    gb.render()


    # Create the Qt Application
    app = QApplication(sys.argv)
    # Create and show the form
    form = Form()
    form.show()
    # Run the main Qt loop
    sys.exit(app.exec_())
