from textual.app import Screen, ComposeResult
from textual.widgets import Button, Header, Select, DataTable
from textual.containers import Horizontal, Vertical
from textual import work

from fs42.station_manager import StationManager
from fs42.catalog import ShowCatalog
from fs42.liquid_manager import LiquidManager
from fs42.ux.dialogs import SelectStationErr, LoadingScreen


class CatalogScreen(Screen):
    CSS_PATH = "catalog_screen.tcss"
    def compose(self) -> ComposeResult:
        yield Header(f"Welcome to Station42")
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
                Button("View Selected", id="view_selected", variant="success"),
                Button("(Re)build Selected", id="rebuild_selected", variant="success"),
                Button("(Re)build All", id="rebuild_all", variant="success"),
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
                    try:
                        catalog = ShowCatalog(StationManager().station_by_name(the_val))
                        
                        self.dt.add_columns("Title", "Tag", "Duration", "Hints")
                        for tag in catalog.clip_index:
                            if tag not in ['sign_off', 'off_air']:
                                for item in catalog.clip_index[tag]:
                                    self.dt.add_row(item.title, item.tag, item.duration, ','.join(map(str, item.hints)))
                    except FileNotFoundError:
                        self.dt.clear(True)
                        self.dt.add_column("Catalog not found.")

            case 'rebuild_selected':
                val = self.select_station.value                
                if(val == Select.BLANK):
                    self.app.push_screen(SelectStationErr())
                else:
                    self.dt.clear(True)
                    (the_val, index) = self.options[val]
                    ls = LoadingScreen()
                    self.app.push_screen(ls)
                    self.rebuild_thread(the_val)
                    
            case 'rebuild_all':
                self.dt.clear(True)
                ls = LoadingScreen()
                self.app.push_screen(ls)
                self.rebuild_all_thread()
                    
            case 'back':
                self.app.pop_screen()
    
    def on_mount(self) -> None:
        self.title = "FieldStation42"
        self.sub_title = "Control Panel"
        self.dt.styles.height = "85%"
        self.dt.styles.width = "100%"
        self.populate_stats()
        
    def on_screen_resume(self):
        self.populate_stats()

    def rebuild_done(self):
        self.app.pop_screen()
        self.populate_stats()

    def update_loading_message(self, message):
        self.app.query_one(LoadingScreen).set_message(message)

    @work(exclusive=True, thread=True)
    def rebuild_thread(self, network_name: str) -> None:
        station = StationManager().station_by_name(network_name)
        if station['network_type'] != 'guide':
            catalog = ShowCatalog(station, rebuild_catalog=True)
        self.app.call_from_thread(self.rebuild_done)

    @work(exclusive=True, thread=True)
    def rebuild_all_thread(self) -> None:
        for station in StationManager().stations:
            msg = f"Building catalog for {station['network_name']}" 
            #self.app.call_from_thread(self.update_loading_message, msg)
            if station['network_type'] != 'guide':
                catalog = ShowCatalog(station, rebuild_catalog=True)
                #catalog.build_catalog()
        self.app.call_from_thread(self.rebuild_done)


    def populate_stats(self):
        self.dt.clear(True)
        self.dt.add_columns("Network",  "Channel", "Type","Tags", "Videos")
        for station in StationManager().stations:
            network_name = station['network_name']
            
            if 'catalog_path' in station:
                try:
                    (vcount, tcount) = ShowCatalog(station).summary_data()
                    self.dt.add_row(network_name, 
                                    station["channel_number"],
                                    station["network_type"],  
                                    vcount, tcount)
                except FileNotFoundError:
                    self.dt.add_row(network_name, 
                                    station["channel_number"],
                                    station["network_type"],  
                                    "No catalog", "No catalog")
            else:
                pass
        