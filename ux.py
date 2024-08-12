from textual.app import App, Screen, ComposeResult
from textual.widgets import DataTable, Static
from textual import events
import pickle
from timings import *
from show_block import ShowBlock, ClipBlock
from field_player import FieldPlayer

#from station_42 import Station42
class ScheduleViewer(Screen):

    CSS_PATH = "ux.tcss"
    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]
    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("SLOT", "POS", "SHOW", "EPISODE", "TAG", "RUNTIME")
        self.fill_table()

    def on_screen_resume(self)->None:
        self.fill_table()

    def fill_table(self):
        table = self.query_one(DataTable)
        table.clear()
        table.focus()

        for hour in OPERATING_HOURS:


            slot = selected_day[hour]
            time_str = f"{hour:02}"
            if hour > 12:
                h = hour - 12
                time_str = f"{h:02}"


            if isinstance(slot, ShowBlock):
                title = slot.front.title
                (show_name, episode_id) = slot.front.title.split("_V1")
                dur = f"{int(slot.front.duration/60):02}:{int(slot.front.duration%60):02}"
                table.add_row(time_str, "00", show_name, f"V1{episode_id}", slot.front.tag, dur)

                if slot.back:
                    title = slot.back.title
                    (show_name, episode_id) = slot.back.title.split("_V1")
                    dur = f"{int(slot.back.duration/60):02}:{int(slot.back.duration%60):02}"
                    table.add_row(time_str, "30", show_name, f"V1{episode_id}", slot.back.tag, dur)
                else:
                    table.add_row(time_str, "30", "continued", f"~", "~", "~")
            elif isinstance(slot, ClipBlock):
                title = slot.name
                show_name = title
                episode_id = slot.tag
                dur = f"{int(slot.duration/60):02}:{int(slot.duration%60):02}"
                table.add_row(time_str, "00", show_name, f"V1{episode_id}", slot.tag, dur)
                table.add_row(time_str, "30", "continued", f"~", "~", "~")
            else:
                print("Unknown show type...")

        #table.fixed_rows = 2
        #table.fixed_columns = 1
        table.cursor_type = "row"
        table.zebra_stripes = True

    def on_data_table_row_selected(self, dt):
        pass
        #index = dt.cursor_row/2 + OPERATING_HOURS[0]

        #slot = selected_day[int(index)]
        #print(slot)
        #day_name = DAYS[day_index]
        #offset = (index % 1)*HOUR
        #field_player.play_slot(day_name, int(index))



class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        welcome_text = f"Welcome to Station42 - for network: {station_config['network_name']}\n"
        welcome_text += f"Schedule generated on:{full_schedule['gen_time']}"
        self.widget1 = Static(welcome_text)
        yield self.widget1
        instuctions = "Press the number for the day of the week you want to view:\n"
        k = 1
        for day in DAYS:
            instuctions += f"{day.capitalize():<20}{k}\n"
            k+=1

        self.widget2 = Static(instuctions)
        yield self.widget2

    def on_mount(self) -> None:
        self.styles.background = "black"
        self.styles.color = "green"
        self.widget1.styles.border = ("solid", "green")
        self.widget2.styles.border = ("solid", "green")
        self.widget1.styles.margin = 2
        self.widget2.styles.margin = 2



class StationViewer(App):

    SCREENS = {"ScheduleViewer": ScheduleViewer(), "WelcomeScreen": WelcomeScreen()}


    def on_mount(self) -> None:
        self.push_screen('WelcomeScreen')

    def on_key(self, event: events.Key) -> None:

        #test if they pressed 1 through 7
        if event.key in map(str, range(1,8)):
            global selected_day
            global day_index
            day_index = int(event.key) - 1
            selected_day = full_schedule[DAYS[day_index]]
            print(f"Selected day: {DAYS[day_index]}")
            print(selected_day)
            self.push_screen('ScheduleViewer')



from confs import abc_conf
station_config = abc_conf.station_conf

full_schedule = None
selected_day = None
day_index = None
#field_player = FieldPlayer(station_config['runtime_dir'])

#open the schedule - were using pickle for expediency
with open(station_config['schedule_path'], "rb") as f:
    full_schedule  = pickle.load(f)

print(full_schedule['gen_time'])

app = StationViewer()
if __name__ == "__main__":
    app.run()
