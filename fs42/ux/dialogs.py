from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Select, LoadingIndicator
from textual.containers import Grid, Vertical

from fs42.station_manager import StationManager


class LoadingScreen(ModalScreen):
    """Screen with a dialog to quit."""

    CSS_PATH = "dialogs.tcss"

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Working on it...", id="question"),
            LoadingIndicator(),
            id="dialog",
        )

    def set_message(self, message) -> None:
        self.query_one(Label).update(message)


class QuitScreen(ModalScreen):
    """Screen with a dialog to quit."""

    CSS_PATH = "dialogs.tcss"

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Are you sure you want to quit?", id="question"),
            Button("Cancel", variant="primary", id="cancel", classes="dialog_button"),
            Button("Quit", variant="error", id="quit", classes="dialog_button"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        else:
            self.app.pop_screen()


class GeneralErr(ModalScreen):
    """Screen with a dialog to quit."""

    CSS_PATH = "dialogs.tcss"

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.message, id="question"),
            Button("Okay", variant="primary", id="quit", classes="dialog_button"),
            id="dialog",
        )

    def __init__(self, message):
        self.message = message
        super().__init__()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()


class SelectStationErr(ModalScreen):
    """Screen with a dialog to quit."""

    CSS_PATH = "dialogs.tcss"

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Please select a station first", id="question"),
            Button("Okay", variant="primary", id="quit", classes="dialog_button"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()


class SelectStationScreen(ModalScreen[str]):
    """Screen with a dialog to quit."""

    CSS_PATH = "dialogs.tcss"

    def compose(self) -> ComposeResult:
        self.options = []
        index = 0
        for station in StationManager().stations:
            self.options.append((station["network_name"], index))
            index += 1
        self.select_station: Select[int] = Select(self.options, id="stationselector")

        yield Grid(
            Label("Select a station", id="question"),
            self.select_station,
            Button("Cancel", variant="primary", id="cmd_cancel", classes="dialog_button"),
            Button("Go!", variant="success", id="cmd_go", classes="dialog_button"),
            id="selectstation_dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cmd_go":
            val = self.select_station.value
            if val == Select.BLANK:
                self.dismiss(None)
            else:
                (the_val, index) = self.options[val]
                self.dismiss(the_val)
        else:
            self.dismiss(None)
