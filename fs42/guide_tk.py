import os
import sys
sys.path.append(os.getcwd())

import tkinter as tk #import Tkinter
from PIL import Image, ImageTk
from fs42.guide_builder import GuideBuilder

class GuideWindowConf:

    def __init__(self, w=720, h=480):
        self.fullscreen = True
        self.width = w
        self.height= h

        self.top_bg = "blue3"
        self.bottom_bg = "blue4"

        self.pad = 10

        self.messages = ["Hello FieldStation42\nGuide preview", "Cheers!\nFrom us to you!", "FieldStation42 Guide\nOn cable mode."]
        self.message_rotation_rate = 10
        self.message_fg = "white"
        self.message_font_family = "Arial"
        self.message_font_size = 25

        self.images = []

        self.network_font_family = "Arial"
        self.network_font_size = 12

        self.schedule_font_family = "Arial"
        self.schedule_font_size = 12
        self.schedule_highlight_fg = "yellow"
        self.schedule_fg = "white"

        self.schedule_border_width = 4
        self.schedule_border_relief = "raised"

        self.footer_messages = ["You are watching FieldStation42", "Now with cable mode."]
        self.footer_height = 50

        self.schedule_row_count = 3

        self.play_sound = False
        self.sound_to_play = "runtime/guide/easy.mp3"

        self._calc_internals()


    def _calc_internals(self):
        self.half_h = self.height/2
        self.half_w = self.width/2
        self.network_w = self.width/6
        self.sched_w = (self.width-self.network_w)/self.schedule_row_count
        self.sched_h = self.half_h/(1+self.schedule_row_count)
        self._message_font = (self.message_font_family, self.message_font_size)
        self._schedule_font = (self.schedule_font_family, self.schedule_font_size)
        self._network_font = (self.network_font_family, self.network_font_size)
        self._message_rotation_rate = self.message_rotation_rate * 1000

    def merge_config(self, to_merge):
        for key in to_merge:
            if hasattr(self, key):
                setattr(self, key, to_merge[key])
        self._calc_internals()



class GuideCommands:
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"

class AdFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.top_bg)


        self.lbl_v = tk.Label(self, text="Video Placeholder", bg='black', fg='white')

        self.lbl_v.place(x=conf.pad,
                        y=conf.pad,
                        width=conf.half_w-conf.pad*2,
                        height=conf.half_h-conf.pad*2
                        )

        self.photo = None
        self.image_index = 0

        self.lbl_messages = tk.Label(self,
                              text="This is the message\nplaceholder",
                              bg=conf.top_bg,
                              fg='white',
                              font=conf._message_font
                              )
        self.lbl_messages.place(x=conf.pad+conf.half_w, y=conf.pad, width=conf.half_w-conf.pad*2, height=conf.half_h-conf.pad*2)

        self.place(x=0, y=0, height=conf.height/2, width=conf.width)
        self.conf = conf
        self.message_index = 0
        self.rotate_message()
        #self.after(self.conf._message_rotation_rate, self.rotate_message)

    def rotate_message(self):
        self.lbl_messages.config(text=self.conf.messages[self.message_index])
        self.message_index+=1
        if self.message_index >= len(self.conf.messages):
            self.message_index = 0

        if len(self.conf.images):
            
            as_img = Image.open(self.conf.images[self.image_index]) 
            resized = as_img.resize((int(self.conf.half_w-self.conf.pad*2),
                                     int(self.conf.half_h-self.conf.pad*2)))
            self.photo =  ImageTk.PhotoImage(resized)
            
            self.lbl_v.configure(image=self.photo)

            self.image_index+=1
            if self.image_index >= len(self.conf.images):
                self.image_index = 0

        self.after(self.conf._message_rotation_rate, self.rotate_message)




class ScheduleFrame(tk.Frame):
    def __init__(self, parent, conf):
        super().__init__(parent, bg=conf.bottom_bg)

        self.conf = conf
        self.populate_frame()
        self.place(x=0, y=conf.half_h, height=conf.half_h, width=conf.width)


    def populate_frame(self):
        gb = GuideBuilder()
        view = gb.build_view()
        lbl_current_time = tk.Label(self,
                            text="Network",
                            bg=self.conf.bottom_bg,
                            fg=self.conf.schedule_highlight_fg,
                            font=self.conf._network_font,
                            borderwidth=self.conf.schedule_border_width,
                            relief=self.conf.schedule_border_relief
                            )
        lbl_current_time.place(x=0, y=0, height=self.conf.sched_h, width=self.conf.network_w)

        l_offset = self.conf.network_w


        for timing in view['timings']:

            lbl_time_slot = tk.Label(self,
                                    text=timing,
                                    bg=self.conf.bottom_bg,
                                    fg=self.conf.schedule_highlight_fg,
                                    font=self.conf._schedule_font,
                                    borderwidth=self.conf.schedule_border_width,
                                    relief=self.conf.schedule_border_relief
                                    )
            lbl_time_slot.place(x=l_offset, y=0, height=self.conf.sched_h, width=self.conf.sched_w)

            l_offset+=self.conf.sched_w

        canvas_h = self.conf.sched_h * len(view['rows']) + self.conf.footer_height*len(self.conf.footer_messages) + 200
        self.canvas = tk.Canvas(self,bg='green',
                                height=self.conf.half_h-self.conf.sched_h,
                                width=self.conf.width,
                                scrollregion=(0,0,canvas_h,self.conf.width)
                                )
        self.canvas.place(x=0, y=self.conf.sched_h)

        self.scroll_frame = tk.Frame(self.canvas, width=self.conf.width, height=canvas_h, bg=self.conf.bottom_bg)

        x_offset = 0
        y_offset = 0
        for r in range(len(view['rows'])):
            x_offset = 0
            row = view['rows'][r]
            meta = view['meta'][r]

            channel_label = tk.Label(self.scroll_frame,
                            text=f"{meta['network_name']}\n{meta['channel_number']}",
                            bg=self.conf.bottom_bg,
                            fg=self.conf.schedule_highlight_fg,
                            font=self.conf._network_font,
                            borderwidth=self.conf.schedule_border_width,
                            relief=self.conf.schedule_border_relief
                            )

            channel_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=int(self.conf.network_w) )

            x_offset = self.conf.network_w

            for c in row:
                if c.width > 0:
                    schedule_label = tk.Label(self.scroll_frame,
                                    text=f"{c.title}",
                                    bg=self.conf.bottom_bg,
                                    fg=self.conf.schedule_fg,
                                    font=self.conf._schedule_font,
                                    anchor="w",
                                    borderwidth=self.conf.schedule_border_width,
                                    relief=self.conf.schedule_border_relief
                                    )

                    the_width = ((self.conf.width-self.conf.network_w)/5400) * c.width
                    
                    schedule_label.place(x=x_offset, y=y_offset, height=int(self.conf.sched_h), width=the_width)
                    x_offset += the_width
                
            y_offset+= self.conf.sched_h
            
    
        self.scroll_frame_id = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor=tk.NW)
        self.after(1000, self.scroll_canvas_view)

        f0, f1 = self.conf.footer_messages

        y_offset = (len(view['rows'])+1) * self.conf.sched_h

        for msg in self.conf.footer_messages:

            #labels that go at the bottom
            lbl_footer = tk.Label(self.scroll_frame,
                            text=msg,
                            bg=self.conf.bottom_bg,
                            fg=self.conf.message_fg,
                            font=self.conf._message_font
                            )
            lbl_footer.place(x=self.conf.pad, y=y_offset, height=self.conf.footer_height, width=self.conf.width-self.conf.pad*2)


        #canvas.yview_moveto(.9)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll_canvas_view(self):
        # get the current bounds
        top, bottom = self.canvas.yview()
        #print(bottom)
        if bottom >= 1.0:
            self.canvas.yview_moveto(-.2)
            self.after(3000, self.scroll_canvas_view)
        else:
            self.canvas.yview_moveto(top+0.001)
            self.after(100, self.scroll_canvas_view)


class GuideApp(tk.Tk):
    def __init__(self, conf, queue=None):
        super().__init__()

        self.conf = conf
        self.title('FieldStation42 Guide')

        if self.conf.fullscreen:
            self.overrideredirect(True)
            #self.attributes('-fullscreen', True)
        
        self.geometry(f"{self.conf.width}x{self.conf.height}")



        #self.resizable(False, False)
        self.after(1000, self.tick)
        self.queue = queue

    def tick(self):
        if self.queue and self.queue.qsize() > 0:
            msg = self.queue.get_nowait()
            if msg == GuideCommands.hide_window:
                print("Guide window is shutting down now.")
                self.destroy()

        self.after(250, self.tick)


def guide_channel_runner(user_conf, queue):
    merge_conf = GuideWindowConf()

    if user_conf:
        merge_conf.merge_config(user_conf)

    app = GuideApp(merge_conf, queue)
    AdFrame(app, merge_conf)
    ScheduleFrame(app, merge_conf)

    app.mainloop()

if __name__ == '__main__':
    guide_channel_runner({}, None)

