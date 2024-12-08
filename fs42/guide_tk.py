from tkinter import *
from tkvideo import TkVideo
from moviepy import VideoFileClip

root = Tk()
my_label = Label(root)
my_label.pack()

clip = VideoFileClip('catalog/indie42_catalog/commercial/December/xmascomms-A_V1-0001.mp4')

player = TkVideo(clip, my_label, loop = 1, size = (720,480))
player.play()

root.mainloop()
