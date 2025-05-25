import logging
import os
import glob
from pathlib import Path

import subprocess
import json

import ffmpeg

USE_EXPERIMENTAL_PROCESS = True

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
        _l = logging.getLogger("MEDIA")
        _l.debug(f"_process_media starting processing for tag={tag} on {len(file_list)} files")
        show_clip_list = []

        #collect list of files that fail
        failed = []

        #get the duration and path for each clip and add to the tag
        for fname in file_list:
            _l.debug(f"--_process_media is working on {fname}")
            # get video file length in seconds
            duration = 0.0
            try:
                if USE_EXPERIMENTAL_PROCESS:
                    #this wont work for mkv and webp and doesnt really save time - shouldn't use unless required 
                    duration = MediaProcessor._get_duration(fname)
                
                #it might not support streams, so check with moviepy
                if duration <= 0.0:
                    video_clip = VideoFileClip(fname)
                    duration = video_clip.duration
                
                #see if both returned 0
                if duration <= 0.0:
                    _l.warning(f"Could not get a duration for tag: {tag}  file: {fname}")
                    _l.warning(f"Files with 0 length can't be added to the catalog.")
                    failed.append(fname)
                else:
                    show_clip = CatalogEntry(fname, duration, tag, hints)
                    show_clip_list.append(show_clip)
                    _l.debug(f"--_process_media is done with {fname}: {show_clip}")

            except Exception as e:
                _l.exception(e)
                _l.error(f"Error processing media file {fname}")
                failed.append(fname)

        _l.debug(f"_process_media completed processing for tag={tag} on {len(file_list)} files")
        
        if len(failed):
            _l.warning(f"Errors were encountered during processing - error count: {len(failed)}")
            count_printed = 0
            for f in failed:
                _l.warning(f)
                count_printed += 1
                if count_printed >= 10:
                    _l.warning(f"and {len(failed)-count_printed} more...")

        return show_clip_list

    @staticmethod
    def _get_duration(file_name):
        probed = ffmpeg.probe(file_name)

        if "streams" in probed and len(probed["streams"]) and "duration" in probed["streams"][0]:
            return float(probed["streams"][0]["duration"])
        else:
            return -1

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
    def _rfind_media(path):
        print("Looking in ", path)
        logging.getLogger("MEDIA").debug(f"_rfind_media scanning for media in {path}")
        file_list = []
        directory = Path(path)

        #get all the files
        for ext in MediaProcessor.supported_formats:
            this_format = directory.rglob(f"*.{ext}")
            file_list += this_format
            #logging.getLogger("MEDIA").debug(f"--Found {len(this_format)} files with {ext} extension - {len(file_list)} total found in {path} so far")


        logging.getLogger("MEDIA").debug(f"_rfind_media done scanning {path} {len(file_list)}")
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
        