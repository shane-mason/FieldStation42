from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)

class WebRender(QMainWindow):
    def __init__(self, user_conf):
        super().__init__()
        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)
        self.user_conf = user_conf

    def navigate(self, URL: str):
        self.browser.setUrl(QUrl(URL))

class WebRenderApp(QApplication):
    def __init__(self, user_conf, queue=None):
        super().__init__([])
        self.user_conf = user_conf
        self.queue = queue
        
        self.window = WebRender(user_conf)
        
        # Set window properties similar to GuideApp
        if "width" in user_conf and "height" in user_conf:
            # Use specified dimensions
            self.window.resize(user_conf["width"], user_conf["height"])
            if "window_decorations" not in user_conf or not user_conf["window_decorations"]:
                self.window.setWindowFlags(Qt.FramelessWindowHint)
            self.window.show()
        else:
            # Go fullscreen by default
            self.window.showFullScreen()
        
        # Set up timer for queue processing
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)  # Check every 250ms

    def tick(self):
        if self.queue and self.queue.qsize() > 0:
            msg = self.queue.get_nowait()
            print(f"WebRender received message: {msg}")
            # Handle queue messages similar to GuideApp
            if hasattr(msg, 'hide_window') or msg == "hide_window":
                print("WebRender window is shutting down now.")
                self.timer.stop()
                self.window.close()
                self.quit()
                return

def web_render_runner(user_conf, queue):
    app = WebRenderApp(user_conf, queue)
    url = user_conf.get("web_url", "http://localhost:4242/static/diagnostics.html")
    # Set default URL if specified in config
    if "url" in user_conf:
        app.window.navigate(user_conf["url"])
    else:
        app.window.navigate(url)
    
    app.exec()

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.getcwd())
    from fs42.station_manager import StationManager
    conf = StationManager().station_by_name("NBC")
    web_render_runner(conf, None)
    
    #https://mwood77.github.io/ws4kp-international/?hazards-checkbox=false&current-weather-checkbox=true&latest-observations-checkbox=false&hourly-checkbox=true&hourly-graph-checkbox=true&travel-checkbox=false&regional-forecast-checkbox=true&local-forecast-checkbox=true&extended-forecast-checkbox=true&almanac-checkbox=true&radar-checkbox=true&marine-forecast-checkbox=true&aqi-forecast-checkbox=true&settings-experimentalFeatures-checkbox=false&settings-hideWebamp-checkbox=false&settings-kiosk-checkbox=true&settings-scanLines-checkbox=false&settings-wide-checkbox=false&chkAutoRefresh=true&settings-windUnits-select=4.00&settings-marineWindUnits-select=1.00&settings-marineWaveHeightUnits-select=1.00&settings-temperatureUnits-select=2.00&settings-distanceUnits-select=2.00&settings-pressureUnits-select=1.00&settings-hoursFormat-select=1.00&settings-speed-select=1.00&latLonQuery=Seattle%2C+WA%2C+USA&latLon=%7B%22lat%22%3A47.6032%2C%22lon%22%3A-122.3302%7D