from textual.app import Screen, ComposeResult
from textual.widgets import Button, Header, Markdown
from textual.containers import Horizontal

from fs42.station_manager import StationManager
from fs42.catalog import ShowCatalog
from fs42.liquid_manager import LiquidManager
from fs42.ux.dialogs import QuitScreen
from fs42.ux.catalog_screen import CatalogScreen
from fs42.ux.schedule_screen import ScheduleScreen


class WelcomeScreen(Screen):
    CSS_PATH = "welcome_screen.tcss"

    def compose(self) -> ComposeResult:
        yield Header("Welcome to Station42")
        self.md = Markdown("LOADING...")
        yield self.md
        yield Horizontal(
            Button("Manage Catalogs", id="manage_catalog", variant="success"),
            Button("Manage Schedules", id="manage_schedule", variant="primary"),
            Button("Exit Application", id="exit", variant="warning"),
            id="welcomebutton",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "manage_catalog":
                self.app.push_screen(CatalogScreen())
            case "manage_schedule":
                self.app.push_screen(ScheduleScreen())
            case "exit":
                self.app.push_screen(QuitScreen())

    def on_mount(self) -> None:
        self.title = "FieldStation42"
        self.sub_title = "Control Panel"
        self.md.styles.height = "80%"
        self.md.styles.width = "100%"
        self.populate_stats()

    def on_screen_resume(self):
        self.populate_stats()

    def populate_stats(self):
        self.md.update("")
        text = "# FieldStation42 Summary\n"

        for station in StationManager().stations:
            network_name = station["network_name"]
            text += f"## Network: {network_name} - Channel #{station['channel_number']} ({station['network_type']})\n"

            if "catalog_path" in station and station["network_type"] not in StationManager().no_catalogs:
                catalog_exists = False
                try:
                    cat = ShowCatalog(station, False)
                    text += f"Catalog summary: {cat.summary()}\n\n"
                    catalog_exists = True
                except FileNotFoundError:
                    text += "Catalog not found. Click 'Manage Catalogs' to build new catalog.\n\n"
                    catalog_exists = False

                (start, end) = (None, None)
                try:
                    (start, end) = LiquidManager().get_extents(network_name)
                except ValueError:
                    text += "* Schedule not found. This is an error - check your configuration.\n"

                if start and end:
                    text += f"* Schedule extents: {start:%Y-%m-%d} to {end:%Y-%m-%d}\n"
                else:
                    if catalog_exists:
                        text += "* Schedule not found. Click 'Manage Schedules' to generate schedules."
                    else:
                        text += "* Schedule not found. After building the catalog, click 'Manage Schedules' to generate schedules."
            else:
                if station["network_type"] in StationManager().no_catalogs:
                    text += f"* {station['network_type']} channels do not have catalogs or schedules\n"
                else:
                    text += "* Catalog not configured or missing - check channel configuration."
            text += "\n"
        self.md.update(text)
