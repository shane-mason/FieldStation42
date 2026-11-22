import tkinter as tk  # import Tkinter
import sys
import os
sys.path.append(os.getcwd())
from fs42.station_manager import StationManager


class DiagWindowConf:
    def __init__(self, w=720, h=480):
        self.fullscreen = True
        self.window_decorations = False

        self.title_font_size = 36
        self.title_font_color = "#FFFFFF"
        self.title_font_family = "Helvetica"

        self.diags_font_size = 24
        self.diags_font_color = "#FFFFFF"
        self.diags_font_family = "Helvetica"
    def _calc_internals(self):
        pass
    def merge_config(self, to_merge):
        for key in to_merge.keys():
            setattr(self, key, to_merge[key])
        return self

class DiagnosticChannel(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent)
        
        # Initialize default fonts and colors
        self.default_font = ("Arial", 12)
        self.default_bg = "white"
        self.default_fg = "black"
        
        # Create the layout
        self._create_widgets()
        
    def _create_widgets(self):
        # Title label at the top
        self.title_label = tk.Label(
            self,
            text="Title",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        # First row of labels (2 columns)
        self.row1_col1_label = tk.Label(
            self,
            text="Row 1, Col 1",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.row1_col1_label.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        
        self.row1_col2_label = tk.Label(
            self,
            text="Row 1, Col 2",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.row1_col2_label.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        # Second row of labels (2 columns)
        self.row2_col1_label = tk.Label(
            self,
            text="Row 2, Col 1",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.row2_col1_label.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        
        self.row2_col2_label = tk.Label(
            self,
            text="Row 2, Col 2",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.row2_col2_label.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        
        # Footer label at the bottom
        self.footer_label = tk.Label(
            self,
            text="Footer",
            font=self.default_font,
            bg=self.default_bg,
            fg=self.default_fg
        )
        self.footer_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        # Configure column weights for responsive layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)




class DiagCommands: 
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"



class DiagnosticApp(tk.Tk):
    def __init__(self, user_conf, queue=None):
        super().__init__()

        self.title("FieldStation42 Guide")

        # set defaults, just in case
        if "width" not in user_conf:
            user_conf["width"] = 720
        if "height" not in user_conf:
            user_conf["height"] = 480

        if "fullscreen" in user_conf and user_conf["fullscreen"]:
            user_conf["width"] = self.winfo_screenwidth()
            user_conf["height"] = self.winfo_screenheight()

        if "window_decorations" not in user_conf or not user_conf["window_decorations"]:
            self.overrideredirect(True)

        self.geometry(f"{user_conf['width']}x{user_conf['height']}")

        merge_conf = DiagWindowConf(w=user_conf["width"], h=user_conf["height"])

        if user_conf:
            merge_conf.merge_config(user_conf)

        self.conf = merge_conf

        # self.resizable(False, False)
        self.after(1000, self.tick)
        self.queue = queue

    def get_conf(self):
        return self.conf

    def tick(self):
        if self.queue and self.queue.qsize() > 0:
            msg = self.queue.get_nowait()
            if msg == DiagCommands.hide_window:
                print("Guide window is shutting down now.")
                self.destroy()

        self.after(250, self.tick)


def diag_channel_runner(user_conf, queue):
    app = DiagnosticApp(user_conf, queue)
    layout = DiagnosticChannel(app, app.get_conf())
    layout.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    app.mainloop()


if __name__ == "__main__":
    conf = StationManager().station_by_name("diagnostic")
    diag_channel_runner(conf, None)