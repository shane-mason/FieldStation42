import signal
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)

class WebRender(QMainWindow):
    def __init__(self):
        super().__init__()
        self.browser = QWebEngineView()

        # Configure QWebEngineSettings to enable autoplay
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        # Set custom user agent for identification
        self.browser.page().profile().setHttpUserAgent("FieldStation42-WebRender/1.0")

        self.setCentralWidget(self.browser)

        # Hide cursor
        self.setCursor(Qt.BlankCursor)

        # Retry logic for handling web server startup races
        self.current_url = None
        self.retry_count = 0
        self.max_retries = 3
        self.retry_delay = 2000  # 2 seconds in milliseconds

    def navigate(self, URL: str):
        # Initialize retry tracking for new URL
        self.current_url = URL
        self.retry_count = 0
        print(f"WebRender navigating to: {URL}")

        self.browser.setUrl(QUrl(URL))
        # Connect to loadFinished to simulate user interaction after page loads
        self.browser.loadFinished.connect(self._on_load_finished)

    def _retry_load(self):
        """Retry loading the current URL"""
        print(f"WebRender retrying URL: {self.current_url} (attempt {self.retry_count + 1}/{self.max_retries})")
        self.browser.setUrl(QUrl(self.current_url))

    def _on_load_finished(self, success):
        if success:
            print(f"WebRender successfully loaded: {self.current_url}")
            # Reset retry count on success
            self.retry_count = 0

            # Inject JavaScript to simulate user interaction and enable autoplay
            js_code = """
            // Simulate user interaction to enable autoplay
            document.body.click();

            // Try to enable wake lock and autoplay for media elements
            if ('wakeLock' in navigator) {
                navigator.wakeLock.request('screen').catch(e => console.log('Wake lock failed:', e));
            }

            // Find and try to play any media elements
            const mediaElements = document.querySelectorAll('video, audio');
            mediaElements.forEach(element => {
                if (element.paused) {
                    element.play().catch(e => console.log('Autoplay failed:', e));
                }
            });
            """
            self.browser.page().runJavaScript(js_code)
        else:
            # Load failed - check if we should retry
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                print(f"WebRender load failed for: {self.current_url}, will retry in {self.retry_delay/1000}s...")
                # Schedule retry after delay
                QTimer.singleShot(self.retry_delay, self._retry_load)
            else:
                print(f"WebRender load failed for: {self.current_url} after {self.max_retries} retries, giving up.")

class WebRenderApp(QApplication):
    def __init__(self, user_conf, queue=None):
        super().__init__([])
        
        self.queue = queue
        
        self.window = WebRender()
        
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
                print("Stopping timer...")
                self.timer.stop()
                print("Closing window...")
                self.window.close()
                print("Quitting application...")
                self.quit()
                print("WebRender shutdown complete")
                return

def web_render_runner(user_conf, queue):
    # Set up signal handler for web process - just exit cleanly
    def web_sigint_handler(sig, frame):
        print("WebRender process received SIGINT, exiting...")
        import sys
        sys.exit(0)
    
    signal.signal(signal.SIGINT, web_sigint_handler)
    
    # Set environment variables to enable autoplay
    import os
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--autoplay-policy=no-user-gesture-required --disable-web-security --allow-running-insecure-content --disable-features=VizDisplayCompositor'
    
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