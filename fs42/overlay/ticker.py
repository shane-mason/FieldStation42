import sys
import signal
import multiprocessing
import os
import tempfile
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtGui import QPixmap, QColor, QPaintEvent, QPainter, QFont, QFontMetrics, QLinearGradient, QPen
from PySide6.QtCore import QTimer, Qt, QPointF, QSharedMemory, QRect
from pathlib import Path


class SingleApplication(QApplication):
    def __init__(self, argv, key):
        super().__init__(argv)
        
        self.lock_file = os.path.join(tempfile.gettempdir(), f"{key}.lock")
        self._running = False
        
        # Check if lock file exists and if the process is actually running
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process is actually running
                try:
                    os.kill(pid, 0)  # Doesn't kill, just checks if process exists
                    self._running = True
                except (OSError, ProcessLookupError):
                    # Process doesn't exist, remove stale lock file
                    os.remove(self.lock_file)
                    self._running = False
            except (ValueError, FileNotFoundError):
                # Invalid lock file, remove it
                try:
                    os.remove(self.lock_file)
                except FileNotFoundError:
                    pass
                self._running = False
        
        if not self._running:
            # Create lock file with current PID
            try:
                with open(self.lock_file, 'w') as f:
                    f.write(str(os.getpid()))
            except IOError:
                raise RuntimeError(f"Unable to create lock file: {self.lock_file}")
    
    def is_running(self):
        return self._running
    
    def __del__(self):
        # Clean up lock file on exit
        if hasattr(self, 'lock_file') and not self._running:
            try:
                os.remove(self.lock_file)
            except FileNotFoundError:
                pass


class TickerWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Make it fullscreen instead of fixed size
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.geometry()
            self.setGeometry(screen_rect)
        
        # Ticker content dimensions
        self.ticker_width = 600
        self.ticker_height = 100
        
        # Styling
        self.header_height = 32
        self.margin = 15
        self.header_text_color = QColor(255, 255, 255)
        
        # Authentic broadcast color schemes
        self.color_schemes = {
            'breaking': {
                'header_start': QColor(220, 0, 0, 240),     # Deep red gradient start
                'header_end': QColor(150, 0, 0, 240),       # Darker red gradient end
                'background': QColor(8, 8, 16, 200),        # Very dark blue-black
                'accent': QColor(255, 255, 255, 80),        # White accent line
                'text_shadow': QColor(0, 0, 0, 150)
            },
            'weather': {
                'header_start': QColor(0, 120, 215, 240),   # Weather channel blue
                'header_end': QColor(0, 80, 160, 240),      # Darker blue
                'background': QColor(12, 24, 40, 200),      # Dark blue-gray
                'accent': QColor(255, 255, 255, 80),
                'text_shadow': QColor(0, 0, 0, 150)
            },
            'sports': {
                'header_start': QColor(0, 150, 60, 240),    # ESPN green
                'header_end': QColor(0, 100, 40, 240),      # Darker green
                'background': QColor(8, 16, 8, 200),        # Very dark green tint
                'accent': QColor(255, 255, 255, 80),
                'text_shadow': QColor(0, 0, 0, 150)
            },
            'financial': {
                'header_start': QColor(255, 140, 0, 240),   # Bloomberg orange
                'header_end': QColor(200, 100, 0, 240),     # Darker orange
                'background': QColor(20, 12, 8, 200),       # Dark orange tint
                'accent': QColor(255, 255, 255, 80),
                'text_shadow': QColor(0, 0, 0, 150)
            },
            'election': {
                'header_start': QColor(180, 0, 0, 240),     # Election red
                'header_end': QColor(0, 0, 180, 240),       # Election blue
                'background': QColor(16, 8, 20, 200),       # Purple-tinted dark
                'accent': QColor(255, 255, 255, 100),
                'text_shadow': QColor(0, 0, 0, 150)
            },
            'fieldstation': {
                'header_start': QColor(40, 80, 140, 240),   # FieldStation42 blue
                'header_end': QColor(20, 50, 90, 240),      # Darker broadcast blue
                'background': QColor(8, 12, 20, 200),       # Dark blue-black
                'accent': QColor(120, 180, 255, 100),       # Light blue accent
                'text_shadow': QColor(0, 0, 0, 150)
            }
        }
        
        # Default values
        self.current_style = 'fieldstation'
        self.header_title = "FS42"
        self.logo_pixmap = None
        self.load_fs42_logo()
        
        # Text scrolling setup
        self.message = ""
        self.scroll_position = 0
        self.iterations = 0
        self.max_iterations = 2
        self.current_iterations = 0
        self.font = QFont("Arial", 20, QFont.Bold)  
        self.header_font = QFont("Arial", 12, QFont.Bold) 
        self.text_color = QColor(255, 255, 255)
        
        # Timer for scrolling animation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scroll_text)
        self.timer.start(50)  
    
    def load_fs42_logo(self):
        """Load FieldStation42 logo if available"""
        logo_paths = [
            Path("runtime/toast_logo.png")
        ]
        
        for logo_path in logo_paths:
            if logo_path.exists():
                self.logo_pixmap = QPixmap(str(logo_path))
                if not self.logo_pixmap.isNull():
                    # Scale logo to fit in header height
                    max_height = int(self.header_height * 0.8)
                    if self.logo_pixmap.height() > max_height:
                        self.logo_pixmap = self.logo_pixmap.scaledToHeight(max_height, Qt.SmoothTransformation)
                    break
        
        if self.logo_pixmap is None or self.logo_pixmap.isNull():
            self.logo_pixmap = None
    
    def show_message(self, text, title="FS42", style="fieldstation", iterations=2):

        self.message = text
        self.header_title = title
        self.current_style = style
        self.max_iterations = iterations
        self.current_iterations = 0
        
        # Update style
        if style in self.color_schemes:
            self.current_style = style
        
        self.scroll_position = self.ticker_width - self.margin  # Start from right edge minus margin
    
    def scroll_text(self):
        if self.message:
            font_metrics = QFontMetrics(self.font)
            text_width = font_metrics.horizontalAdvance(self.message)
            
            self.scroll_position -= 2  # Scroll speed
            
            if self.scroll_position < -text_width:
                self.current_iterations += 1
                self.scroll_position = self.ticker_width - self.margin
                
                if self.current_iterations >= self.max_iterations:
                    print(f"Completed {self.current_iterations} iterations. Exiting...")
                    QApplication.quit()
                    return
            
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate bottom area for ticker content
        ticker_x = (self.width() - self.ticker_width) // 2
        ticker_y = self.height() - self.ticker_height - 50
        ticker_rect = QRect(ticker_x, ticker_y, self.ticker_width, self.ticker_height)
        
        # Use default style if current style is invalid
        try:
            scheme = self.color_schemes[self.current_style]
        except KeyError:
            print(f"Warning: Style '{self.current_style}' not found, using default 'fieldstation' style")
            scheme = self.color_schemes['fieldstation']
        
        # Draw main background with rounded corners in bottom area only
        main_rect = ticker_rect.adjusted(2, self.header_height, -2, -2)
        painter.setBrush(scheme['background'])
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(main_rect, 4, 4)
        
        # Draw header tab on the left side within ticker area
        font_metrics = QFontMetrics(self.header_font)
        text_width = font_metrics.horizontalAdvance(self.header_title)
        logo_width = self.logo_pixmap.width() + 8 if self.logo_pixmap else 0  # 8px padding
        tab_width = text_width + logo_width + self.margin * 2
        header_rect = ticker_rect.adjusted(2, 2, -(self.ticker_width - tab_width - 2), -(self.ticker_height - self.header_height))
        
        # Create gradient for header tab
        gradient = QLinearGradient(0, header_rect.top(), 0, header_rect.bottom())
        gradient.setColorAt(0, scheme['header_start'])
        gradient.setColorAt(1, scheme['header_end'])
        
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(header_rect, 6, 6)
        
        # Draw bottom part of header tab to make it rectangular on bottom
        bottom_rect = header_rect.adjusted(0, header_rect.height() // 2, 0, 0)
        painter.drawRect(bottom_rect)
        
        # Draw subtle accent line at bottom of header tab
        painter.setPen(QPen(scheme['accent'], 1))
        painter.drawLine(QPointF(header_rect.bottomLeft()) + QPointF(6, 0), 
                        QPointF(header_rect.bottomRight()) - QPointF(6, 0))
        
        # Draw logo and header text
        painter.setFont(self.header_font)
        
        current_x = header_rect.left() + self.margin
        
        # Draw logo if available
        if self.logo_pixmap:
            logo_y = header_rect.top() + (header_rect.height() - self.logo_pixmap.height()) // 2
            painter.drawPixmap(current_x, logo_y, self.logo_pixmap)
            current_x += self.logo_pixmap.width() + 8  # 8px spacing
        
        # Calculate text rect
        text_rect = header_rect.adjusted(current_x - header_rect.left(), 0, -self.margin, 0)
        
        # Text shadow
        painter.setPen(scheme['text_shadow'])
        shadow_rect = text_rect.adjusted(1, 1, 1, 1)
        painter.drawText(shadow_rect, Qt.AlignLeft | Qt.AlignVCenter, self.header_title)
        
        # Main text
        painter.setPen(self.header_text_color)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.header_title)

        # Draw scrolling text in main area (adjusted for ticker area)
        if self.message:
            painter.setFont(self.font)
            
            text_y = ticker_y + self.header_height + (main_rect.height() // 2) + 6
            
            clip_rect = main_rect.adjusted(self.margin, 4, -self.margin, -4)
            painter.setClipRect(clip_rect)

            painter.setPen(scheme['text_shadow'])
            painter.drawText(ticker_x + self.scroll_position + 1, text_y + 1, self.message)

            painter.setPen(self.text_color)
            painter.drawText(ticker_x + self.scroll_position, text_y, self.message)
        
        # End the painter to avoid backing store warnings
        painter.end()

    def resizeEvent(self, event):
        self.update()

    def mousePressEvent(self, event):
        pass


def signal_handler(sig, frame):
    print("\nShutting down...")
    QApplication.quit()


def run_ticker_app(text, title="FS42", style="fieldstation", iterations=2):
    """Run the ticker application with specified parameters"""
    print("Running news ticker window...")
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SingleApplication(sys.argv, "FS42_Ticker_SingleInstance")
    
    if app.is_running():
        print("Ticker is already running!")
        sys.exit(1)
    
    window = TickerWindow()
    window.show_message(text, title, style, iterations)
    window.show()
    
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)
    
    sys.exit(app.exec())


def run_ticker(text, title="FS42", style="fieldstation", iterations=2):
    """Start the ticker in a separate process"""
    def ticker_process():
        run_ticker_app(text, title, style, iterations)
    
    process = multiprocessing.Process(target=ticker_process)
    process.start()
    return process


if __name__ == '__main__':
    # Example usage when run directly
    run_ticker_app("Welcome to FieldStation42 - Your retro TV experience")
    print("Done")