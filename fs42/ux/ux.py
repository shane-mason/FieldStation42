from textual.app import App
from fs42.ux.welcome_screen import WelcomeScreen

class StationApp(App):

    SCREENS = {"WelcomeScreen": WelcomeScreen}


    def on_mount(self) -> None:
        self.push_screen('WelcomeScreen')


if __name__ == "__main__":
    app = StationApp()
    app.run()