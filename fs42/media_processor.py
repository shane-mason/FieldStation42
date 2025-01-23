import logging
import os
import glob

try:
    #try to import from version > 2.0
    from moviepy import VideoFileClip
except ImportError: 
    #fall back to import from version 1.0
    from moviepy.editor import VideoFileClip # type: ignore

from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint, BumpHint, DayPartHint
from fs42.catalog_entry import CatalogEntry

class MediaProcessor:
    supported_formats = ["mp4", "mpg", "mpeg", "avi", "mov", "mkv"]

    @staticmethod
    def _process_media(file_list, tag, hints=[]):
        logging.getLogger("MEDIA").debug(f"_process_media starting processing for tag={tag} on {len(file_list)} files")
        show_clip_list = []
        #get the duration and path for each clip and add to the tag
        for fname in file_list:
            logging.getLogger("MEDIA").debug(f"--_process_media is working on {fname}")
            # get video file length in seconds
            video_clip = VideoFileClip(fname)
            show_clip = CatalogEntry(fname, video_clip.duration, tag, hints)
            show_clip_list.append(show_clip)
            logging.getLogger("MEDIA").debug(f"--_process_media is done with {fname}: {show_clip}")

        logging.getLogger("MEDIA").debug(f"_process_media completed processing for tag={tag} on {len(file_list)} files")

        return show_clip_list


    @staticmethod
    def _find_media(path):
        logging.getLogger("MEDIA").debug(f"_find_media scanning for media in {path}")
        file_list = []
        for ext in MediaProcessor.supported_formats:
            this_format = glob.glob(f"{path}/*.{ext}")
            file_list += this_format
            logging.getLogger("MEDIA").debug(f"--Found {len(this_format)} files with {ext} extension - {len(file_list)} total found in {path} so far")
 
        logging.getLogger("MEDIA").debug(f"_find_media done scanning {path} {len(file_list)}")
        return file_list

    @staticmethod
    def _process_hints(path, tag, bumpdir=False):
        base = os.path.basename(path)
        hints = []
        if MonthHint.test_pattern(base):
            hints.append(MonthHint(base))
        if QuarterHint.test_pattern(base):
            hints.append(QuarterHint(base))
        if RangeHint.test_pattern(base):
            hints.append(RangeHint(base))
        if DayPartHint.test_pattern(base):
            hints.append(DayPartHint(base))
        if bumpdir:
            if BumpHint.test_pattern(base):
                hints.append(BumpHint(base))

        return hints

    @staticmethod
    def _process_subs(dir_path, tag, bumpdir=False):
        subs = [ f.path for f in os.scandir(dir_path) if f.is_dir() ]
        clips = []
        for sub in subs:
            file_list = MediaProcessor._find_media(sub)
            hints = MediaProcessor._process_hints(sub, tag, bumpdir)
            clips += MediaProcessor._process_media(file_list, tag, hints=hints)
        return clips

    @staticmethod
    def _test_candidate_hints(hint_list, when):
        for hint in hint_list:
            if hint.hint(when) == False:
                return False
        return True
    
    @staticmethod
    def _by_position(bumps, pre_tag, post_tag):
        pre = []
        fill = []
        post = []
        
        for bump in bumps:
            found = False
            for hint in bump.hints:
                if type(hint) is BumpHint:
                    if hint.where == BumpHint.pre:
                        bump.tag = pre_tag
                        pre.append(bump)
                        found = True
                    elif hint.where == BumpHint.post:
                        bump.tag = post_tag
                        post.append(bump)
                        found = True

            if not found:
                fill.append(bump)
        return (pre, fill, post)
        