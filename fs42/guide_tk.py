import os
import sys
sys.path.append(os.getcwd())

import tkinter as tk #import Tkinter

from fs42.guide_builder import GuideBuilder
from confs.fieldStation42_conf import main_conf

class GuideWindowConf:

    def __init__(self, w=720, h=480):
        self.width = w
        self.height= h
        self.top_bg = "blue3"
        self.bot_bg = "blue4"
        self._calc_internals()
        self.pad = 10
        self.message_font = ("Arial", 25)
        self.schedule_font = ("Arial", 15)
        self.network_font = ("Arial", 12)
        self.schedule_highlight_fg = "yellow"
        self.schedule_fg = "white"
        self.message_fg = "white"
        self.schedule_border_width = 4
        self.schedule_border_relief = "raised"
        self.footer_messages = ("You are watching FieldStation42", "Now with cable mode.")
        self.footer_height = 50

    def _calc_internals(self):
        self.half_h = self.height/2
        self.half_w = self.width/2
        self.network_w = self.width/6
        self.sched_w = (self.width-self.network_w)/3
        self.sched_h = self.half_h/4

class AdFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.top_bg)

        self.lbl_v = tk.Label(self, text="Video Placeholder", bg='black', fg='white')

        self.lbl_v.place(x=conf.pad,
                         y=conf.pad,
                         width=conf.half_w-conf.pad*2,
                         height=conf.half_h-conf.pad*2
                         )

        self.lbl_v = tk.Label(self,
                              text="This is the message\nplaceholder",
                              bg=conf.top_bg,
                              fg='white',
                              font=conf.message_font
                              )
        self.lbl_v.place(x=conf.pad+conf.half_w, y=conf.pad, width=conf.half_w-conf.pad*2, height=conf.half_h-conf.pad*2)

        self.place(x=0, y=0, height=conf.height/2, width=conf.width)
        self.conf = conf
        print("Top frame initialized")


class ScheduleFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.bot_bg)

        self.conf = conf
        self.populate_frame()
        self.place(x=0, y=conf.half_h, height=conf.half_h, width=conf.width)

        print("Bottom frame initialized")

    def populate_frame(self):
        gb = GuideBuilder()
        gb.load_schedules(main_conf['stations'])
        view = gb.build_view()
        print(view)

        lbl = tk.Label(self,
                        text="Network",
                        bg=self.conf.bot_bg,
                        fg=self.conf.schedule_highlight_fg,
                        font=self.conf.network_font,
                        borderwidth=self.conf.schedule_border_width,
                        relief=self.conf.schedule_border_relief
                        )
        lbl.place(x=0, y=0, height=self.conf.sched_h, width=self.conf.network_w)

        l_offset = self.conf.network_w


        for timing in view['timings']:
            print(timing)
            lbl = tk.Label(self,
                            text=timing,
                            bg=self.conf.bot_bg,
                            fg=self.conf.schedule_highlight_fg,
                            font=self.conf.schedule_font,
                            borderwidth=self.conf.schedule_border_width,
                            relief=self.conf.schedule_border_relief
                            )
            lbl.place(x=l_offset, y=0, height=self.conf.sched_h, width=self.conf.sched_w)
            l_offset+=self.conf.sched_w


        self.canvas = tk.Canvas(self,bg='green', height=self.conf.half_h-self.conf.sched_h, width=self.conf.width, scrollregion=(0,0,1000,1000))
        self.canvas.place(x=0, y=self.conf.sched_h)

        self.scroll_frame = tk.Frame(self.canvas, width=1000, height=1000, bg=self.conf.bot_bg)


        x_offset = 0
        y_offset = 0
        for r in range(len(view['rows'])):
            x_offset = 0
            row = view['rows'][r]
            meta = view['meta'][r]
            print(meta, row)

            channel_label = tk.Label(self.scroll_frame,
                            text=f"{meta['network_name']}\n{meta['channel_number']}",
                            bg=self.conf.bot_bg,
                            fg=self.conf.schedule_highlight_fg,
                            font=self.conf.network_font,
                            borderwidth=self.conf.schedule_border_width,
                            relief=self.conf.schedule_border_relief
                            )

            channel_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=int(self.conf.network_w) )

            x_offset = self.conf.network_w

            for c in row:

                if c.width > 0:
                    schedule_label = tk.Label(self.scroll_frame,
                                    text=f"{c.title}",
                                    bg=self.conf.bot_bg,
                                    fg=self.conf.schedule_fg,
                                    font=self.conf.network_font,
                                    borderwidth=self.conf.schedule_border_width,
                                    relief=self.conf.schedule_border_relief
                                    )

                    schedule_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=int(self.conf.sched_w*c.width))
                    x_offset += self.conf.sched_w*c.width

            y_offset+= self.conf.sched_h

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor=tk.NW)
        self.after(1000, self.tick)

        f0, f1 = self.conf.footer_messages

        y_offset = (len(view['rows'])+1) * self.conf.sched_h

        #labels that go at the bottom
        lbl_footer0 = tk.Label(self.scroll_frame,
                        text=f0,
                        bg=self.conf.bot_bg,
                        fg=self.conf.message_fg,
                        font=self.conf.message_font
                        )
        lbl_footer0.place(x=self.conf.pad, y=y_offset, height=self.conf.footer_height, width=self.conf.width-self.conf.pad*2)

        lbl_footer1 = tk.Label(self.scroll_frame,
                        text=f1,
                        bg=self.conf.bot_bg,
                        fg=self.conf.schedule_highlight_fg,
                        font=self.conf.message_font
                        )
        y_offset += self.conf.footer_height
        lbl_footer1.place(x=self.conf.pad, y=y_offset, height=self.conf.footer_height, width=self.conf.width-self.conf.pad*2)

        #canvas.yview_moveto(.9)

    def tick(self):
        #print("In the tick")
        #print(self.canvas.yview())
        top, bottom = self.canvas.yview()
        self.canvas.yview_moveto(top+0.0005)
        self.after(50, self.tick)


class App(tk.Tk):
    def __init__(self, conf):
        super().__init__()

        self.title('FieldStation42 Guide')
        self.geometry(f"{conf.width}x{conf.height}")
        #self.resizable(False, False)


if __name__ == '__main__':
    confx = GuideWindowConf()

    app = App(confx)
    AdFrame(app, confx)
    ScheduleFrame(app, confx)
    app.mainloop()
