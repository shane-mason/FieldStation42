import os

from textual.app import Screen, ComposeResult
from textual.widgets import Button, Header, Select, DataTable
from textual.containers import Horizontal, Vertical
from textual import work

from fs42.station_manager import StationManager
from fs42.liquid_schedule import LiquidSchedule
from fs42.catalog import ShowCatalog
from fs42.liquid_manager import LiquidManager
from fs42.ux.dialogs import SelectStationErr, LoadingScreen, GeneralErr


class ScheduleScreen(Screen):
    CSS_PATH = "catalog_screen.tcss"
    def compose(self) -> ComposeResult:
        yield Header("Welcome to Station42")
        self.dt = DataTable()

        self.options = []
        index = 0
        for station in StationManager().stations:
            if station['network_type'] != "guide":
                self.options.append((station['network_name'], index))   
                index+=1 
        self.select_station: Select[int] =  Select(self.options, id="stationselector", prompt="Select Station")

        yield Vertical(
            Horizontal(
                self.select_station,
                Button("View Selected", id="view_selected", variant="primary"),
                Button("(Re)Build All", id="rebuild_all", variant="primary"),
                Button("Add Month", id="add_time", variant="primary"),
                Button("Back", id="back", variant="warning") 
            ),
            self.dt,
            id="catalogscreen"
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:

        match event.button.id:
            case 'view_selected':
                
                val = self.select_station.value
                
                if(val == Select.BLANK):
                    self.app.push_screen(SelectStationErr())
                else:
                    self.dt.clear(True)
                    (the_val, index) = self.options[val]
                
                    schedule = LiquidManager().get_schedule_by_name(the_val)
                    if schedule is None:
                        self.dt.clear(True)
                        self.dt.add_column("Schedule not found.")
                    else:
                        #f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"
                        self.dt.add_columns("Start Time", "End Time", "Title", "Duration", "Blocks")
                        for _block in schedule:
                            duration = _block.end_time - _block.start_time
                            self.dt.add_row(_block.start_time.strftime('%m/%d %H:%M'), 
                                            _block.end_time.strftime('%H:%M'), 
                                            _block.title,
                                            round(duration.total_seconds()/60, 2),
                                            len(_block.plan))
                    
            case 'rebuild_all':
                #first, check that all catalogs exist:
                all_found = self.all_catalogs_found()

                if all_found:                    
                    self.dt.clear(True)
                    ls = LoadingScreen()
                    self.app.push_screen(ls)
                    self.rebuild_all_thread()
                else:
                    es = GeneralErr("Some stations do not have catalogs built. Select 'Back' and then 'Manage Catalogs' to build.")
                    self.app.push_screen(es)

            case 'add_time':
                all_found = self.all_catalogs_found()

                if all_found:     
                    self.dt.clear(True)
                    ls = LoadingScreen()
                    self.app.push_screen(ls)
                    self.addtime_thread("month")
                else:
                    es = GeneralErr("Some stations do not have catalogs built. Select 'Back' and then 'Manage Catalogs' to build.")
                    self.app.push_screen(es)                    
            case 'back':
                self.app.pop_screen()
    
    def on_mount(self) -> None:
        self.title = "FieldStation42"
        self.sub_title = "Control Panel"
        self.dt.styles.height = "85%"
        self.dt.styles.width = "100%"
        self.populate_stats()
        
    def rebuild_done(self):
        LiquidManager().reload_schedules()
        self.app.pop_screen()
        self.populate_stats()

    def update_loading_message(self, message):
        self.app.query_one(LoadingScreen).set_message(message)

    @work(exclusive=True, thread=True)
    def addtime_thread(self, how_long: str) -> None:
        stations = StationManager().stations
        for station in stations:
            if 'schedule_path' in station:
                schedule = LiquidSchedule(station)
                schedule.add_month()
        self.app.call_from_thread(self.rebuild_done)

    @work(exclusive=True, thread=True)
    def rebuild_all_thread(self) -> None:
        for station in StationManager().stations:
            if 'schedule_path' in station:
                if os.path.exists(station["schedule_path"]):
                    os.unlink(station["schedule_path"])
                LiquidSchedule(station).add_month()
        self.app.call_from_thread(self.rebuild_done)


    def all_catalogs_found(self):
        all_found = True
        for station in StationManager().stations:
            try:
                if station['network_type'] != 'guide':
                    ShowCatalog(station)
            except FileNotFoundError:
                all_found = False
                break
        return all_found


    def populate_stats(self):
        
        self.dt.clear(True)
        self.dt.add_columns("Network Name", "Schedule Start Date", "Schedule End Date", "Days")
        schedules = LiquidManager().schedules
        for key in schedules:
            (_start, _end) = LiquidManager().get_extents(key)
            if _start and _end:
                diff = _end - _start
                self.dt.add_row(key, f"{_start:%Y-%m-%d}", f"{_end:%Y-%m-%d}", f"{diff.days}")
            else:
                self.dt.add_row(key, "No Schedule", "", "")
