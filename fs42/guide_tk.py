import os
import sys
import datetime
import glob

sys.path.append(os.getcwd())

import tkinter as tk  # import Tkinter
from PIL import Image, ImageTk
from fs42.guide_builder import GuideBuilder
from fs42.station_manager import StationManager


class GuideWindowConf:
    def __init__(self, w=720, h=480):
        self.fullscreen = True

        self.width = w
        self.height = h

        self.top_bg = "blue3"
        self.bottom_bg = "blue4"

        self.pad = 10

        self.messages = [
            "Hello FieldStation42\nGuide preview",
            "Cheers!\nFrom us to you!",
            "FieldStation42 Guide\nOn cable mode.",
        ]
        self.message_rotation_rate = 10
        self.message_fg = "white"
        self.message_font_family = "Arial"
        self.message_font_size = 25

        self.images = []

        self.network_font_family = "Arial"
        self.network_font_size = 12
        self.network_width_divisor = 6.0

        self.schedule_font_family = "Arial"
        self.schedule_font_size = 12
        self.schedule_highlight_fg = "yellow"
        self.schedule_fg = "white"

        self.schedule_border_width = 4
        self.schedule_border_relief = "raised"

        self.footer_messages = ["You are watching FieldStation42", "Now with cable mode."]
        self.footer_height = 50

        self.schedule_row_count = 3
        self.schedule_col_count = 3

        self.play_sound = False
        self.sound_to_play = None
        self.normalize_titles = True

        self.scroll_speed = 1.0

        # Ratio of top section height to total height (0.0 to 1.0)
        # 0.5 = 50/50 split, 0.3 = 30% top / 70% bottom, etc.
        self.top_section_ratio = 0.5

        # Row height constraints for responsive sizing
        self.target_row_height = 60  # Target height for schedule rows
        self.min_row_height = 40     # Minimum height for schedule rows
        self.max_row_height = 80     # Maximum height for schedule rows

        self._calc_internals()

    def _calc_internals(self):
        self.half_h = self.height / 2
        self.half_w = self.width / 2

        # Calculate section heights based on configurable ratio
        self.top_section_height = self.height * self.top_section_ratio
        self.bottom_section_height = self.height * (1.0 - self.top_section_ratio)

        self.network_w = self.width / self.network_width_divisor
        self.sched_w = (self.width - self.network_w) / self.schedule_col_count

        # Calculate responsive row height with constraints
        # First, calculate how much space is available for rows (minus the header row)
        available_height = self.bottom_section_height

        # Try to use target row height for header + rows
        total_rows = 1 + self.schedule_row_count  # 1 header + schedule rows
        calculated_height = available_height / total_rows

        # Constrain row height to min/max bounds
        self.sched_h = max(self.min_row_height, min(self.max_row_height, calculated_height))

        # Calculate how many visible rows we can actually fit
        self.visible_row_count = int((available_height - self.sched_h) / self.sched_h)

        self._message_font = (self.message_font_family, self.message_font_size)
        self._schedule_font = (self.schedule_font_family, self.schedule_font_size)
        self._network_font = (self.network_font_family, self.network_font_size)
        self._message_rotation_rate = self.message_rotation_rate * 1000

    def merge_config(self, to_merge):
        for key in to_merge:
            if hasattr(self, key):
                setattr(self, key, to_merge[key])
        self._calc_internals()

    def check_config(self, merge_conf):
        """Note: this should only be called from the startup checker since it merges the conf again"""
        self.merge_config(merge_conf)
        to_check = self.images.copy()

        # Check sound_to_play - can be a string (file or directory) or a list of files
        if self.play_sound and self.sound_to_play:
            if isinstance(self.sound_to_play, list):
                # It's a list - check each file
                for sound_file in self.sound_to_play:
                    to_check.append(sound_file)
            elif isinstance(self.sound_to_play, str):
                # It's a string - could be a file or directory
                if os.path.isdir(self.sound_to_play):
                    # Directory path - check if it has any mp3 files
                    mp3_files = glob.glob(os.path.join(self.sound_to_play, "*.mp3"))
                    if not mp3_files:
                        errors = [f"Guide channel directory {self.sound_to_play} exists but contains no .mp3 files"]
                        return errors
                else:
                    # Single file path - add to check list
                    to_check.append(self.sound_to_play)

        errors = []
        for fp in to_check:
            if not os.path.exists(fp):
                err = f"Guide channel config references a file named {fp} but it does not exist on disk"
                errors.append(err)

        # check that its fullscreen, or else that width and height are specified
        if not self.fullscreen:
            if not self.width or not self.height:
                err = """Guide channel fullscreen is set to false, but width or height is not speficied.
                If fullscreen is not set to true, please set both width and height in pixels.
                """
                errors.append(err)
        return errors


class GuideCommands:
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"


class AdFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.top_bg)

        self.lbl_v = tk.Label(self, text="Video Placeholder", bg="black", fg="white")

        self.lbl_v.place(x=conf.pad, y=conf.pad, width=conf.half_w - conf.pad * 2, height=conf.top_section_height - conf.pad * 2)

        self.photo = None
        self.image_index = 0

        self.lbl_messages = tk.Label(
            self, text="This is the message\nplaceholder", bg=conf.top_bg, fg="white", font=conf._message_font
        )
        self.lbl_messages.place(
            x=conf.pad + conf.half_w, y=conf.pad, width=conf.half_w - conf.pad * 2, height=conf.top_section_height - conf.pad * 2
        )

        self.place(x=0, y=0, height=conf.top_section_height, width=conf.width)
        self.conf = conf
        self.message_index = 0
        self.rotate_message()
        # self.after(self.conf._message_rotation_rate, self.rotate_message)

    def rotate_message(self):
        self.lbl_messages.config(text=self.conf.messages[self.message_index])
        self.message_index += 1
        if self.message_index >= len(self.conf.messages):
            self.message_index = 0

        if len(self.conf.images):
            try:
                as_img = Image.open(self.conf.images[self.image_index])
                # Calculate maximum size for the image area
                max_width = int(self.conf.half_w - self.conf.pad * 2)
                max_height = int(self.conf.top_section_height - self.conf.pad * 2)

                # Use thumbnail to preserve aspect ratio (fits within max size)
                as_img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(as_img)

                self.lbl_v.configure(image=self.photo)

                self.image_index += 1
                if self.image_index >= len(self.conf.images):
                    self.image_index = 0
            except Exception as e:
                print(e)
                print("Error while loading files from guide configuration.")
                print("Do you have files specified in the guide configuration that don't exist on disk?")
                # exit(-1)
        self.after(self.conf._message_rotation_rate, self.rotate_message)


class ScheduleFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.bottom_bg)
        self.parent = parent
        self.conf = conf
        self.populate_frame()
        self.place(x=0, y=conf.top_section_height, height=conf.bottom_section_height, width=conf.width)
        self.start_time = datetime.datetime.now()

    def populate_frame(self):
        gb = GuideBuilder()
        
        self.lbl_current_time = tk.Label(
            self,
            text="Network",
            bg=self.conf.bottom_bg,
            fg=self.conf.schedule_highlight_fg,
            font=self.conf._network_font,
            borderwidth=self.conf.schedule_border_width,
            relief=self.conf.schedule_border_relief,
        )
        self.lbl_current_time.place(x=0, y=0, height=self.conf.sched_h, width=self.conf.network_w)

        l_offset = self.conf.network_w
        view = gb.build_view(normalize=self.conf.normalize_titles)
        for timing in view["timings"]:
            lbl_time_slot = tk.Label(
                self,
                text=timing,
                bg=self.conf.bottom_bg,
                fg=self.conf.schedule_highlight_fg,
                font=self.conf._schedule_font,
                borderwidth=self.conf.schedule_border_width,
                relief=self.conf.schedule_border_relief,
            )
            lbl_time_slot.place(x=l_offset, y=0, height=self.conf.sched_h, width=self.conf.sched_w)

            l_offset += self.conf.sched_w

        canvas_h = (
            self.conf.sched_h * len(view["rows"]) + self.conf.footer_height * len(self.conf.footer_messages) + 200
        )
        self.canvas = tk.Canvas(
            self,
            bg="green",
            height=self.conf.bottom_section_height - self.conf.sched_h,
            width=self.conf.width,
            scrollregion=(0, 0, canvas_h, self.conf.width),
        )
        self.canvas.place(x=0, y=self.conf.sched_h)

        # Initialize scroll speed (1.0 = normal speed, 0 = no scrolling)
        self.scroll_speed = self.conf.scroll_speed

        self.scroll_frame = tk.Frame(self.canvas, width=self.conf.width, height=canvas_h, bg=self.conf.bottom_bg)

        x_offset = 0
        y_offset = 0
        for r in range(len(view["rows"])):
            x_offset = 0
            row = view["rows"][r]
            meta = view["meta"][r]

            channel_label = tk.Label(
                self.scroll_frame,
                text=f"{meta['network_name']}\n{meta['channel_number']}",
                bg=self.conf.bottom_bg,
                fg=self.conf.schedule_highlight_fg,
                font=self.conf._network_font,
                borderwidth=self.conf.schedule_border_width,
                relief=self.conf.schedule_border_relief,
            )

            channel_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=int(self.conf.network_w))
            self.update_time()

            x_offset = self.conf.network_w

            for c in row:
                if c.width > 0:
                    schedule_label = tk.Label(
                        self.scroll_frame,
                        text=f"{c.title}",
                        bg=self.conf.bottom_bg,
                        fg=self.conf.schedule_fg,
                        font=self.conf._schedule_font,
                        anchor="w",
                        borderwidth=self.conf.schedule_border_width,
                        relief=self.conf.schedule_border_relief,
                    )

                    the_width = ((self.conf.width - self.conf.network_w) / 5400) * c.width

                    schedule_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=the_width)
                    x_offset += the_width

            y_offset += self.conf.sched_h

        self.scroll_frame_id = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor=tk.NW)
        self.after(1000, self.scroll_canvas_view)


        y_offset = (len(view["rows"]) + 1) * self.conf.sched_h

        for msg in self.conf.footer_messages:
            # labels that go at the bottom
            lbl_footer = tk.Label(
                self.scroll_frame,
                text=msg,
                bg=self.conf.bottom_bg,
                fg=self.conf.message_fg,
                font=self.conf._message_font,
            )
            lbl_footer.place(
                x=self.conf.pad, y=y_offset, height=self.conf.footer_height, width=self.conf.width - self.conf.pad * 2
            )

        # canvas.yview_moveto(.9)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll_canvas_view(self):
        # If scroll speed is zero, don't scroll at all
        if self.scroll_speed == 0:
            self.after(100, self.scroll_canvas_view)
            return

        # get the current bounds
        top, bottom = self.canvas.yview()
        # print(bottom)
        if bottom >= 1.0:
            diff = datetime.datetime.now() - self.start_time
            # check to see if its been more than a minute since we started
            if diff > datetime.timedelta(minutes=1):
                self.refresh()
                return
            else:
                # Cool slide transition: animate back to top
                self.slide_to_top(steps=20, current_step=0)
                return
        else:
            # Continue scrolling up (moving view down in content)
            self.canvas.yview_moveto(top + 0.001)

        # Calculate delay based on scroll speed (higher speed = shorter delay)
        delay = int(100 / self.scroll_speed) if self.scroll_speed > 0 else 100
        self.after(delay, self.scroll_canvas_view)

    def slide_to_top(self, steps, current_step):
        if current_step >= steps:
            # Animation complete, resume normal scrolling
            self.canvas.yview_moveto(0.0)
            self.after(100, self.scroll_canvas_view)
            return
        
        # Calculate eased position (ease-out effect)
        progress = current_step / steps
        eased_progress = 1 - (1 - progress) ** 3  # cubic ease-out
        
        # Animate from current position (1.0) to top (0.0)
        current_pos = 1.0 - eased_progress
        self.canvas.yview_moveto(current_pos)
        
        # Continue animation
        self.after(50, lambda: self.slide_to_top(steps, current_step + 1))

    def update_time(self):
        time_f = StationManager().server_conf["time_format"]
        current_time = datetime.datetime.now().strftime(time_f)

        self.lbl_current_time.config(text=current_time)
        self.after(1000, self.update_time)

    def refresh(self):
        self.destroy()
        self.__init__(self.parent, self.conf)


class GuideApp(tk.Tk):
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

        merge_conf = GuideWindowConf(w=user_conf["width"], h=user_conf["height"])

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
            if msg == GuideCommands.hide_window:
                print("Guide window is shutting down now.")
                self.destroy()

        self.after(250, self.tick)


def guide_channel_runner(user_conf, queue):
    app = GuideApp(user_conf, queue)
    AdFrame(app, app.get_conf())
    ScheduleFrame(app, app.get_conf())

    app.mainloop()


if __name__ == "__main__":
    conf = StationManager().station_by_name("Guide")
    guide_channel_runner(conf, None)
