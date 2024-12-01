import os
import glob
import logging
import pickle
import sys
import random
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint
try:
    #try to import from version > 2.0
    from moviepy import VideoFileClip
except ImportError:
    #fall back to import from version 1.0
    from moviepy.editor import VideoFileClip


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class ShowClip:
    def __init__(self, path, duration, tag, hints=[]):
        self.path = path
        #get the show name from the path
        self.title = os.path.basename(path).split(".")[0]
        self.duration = duration
        self.tag = tag
        self.count = 0
        self.hints = hints

    def __str__(self):
        return f"{self.title:<20.20} | {self.tag:<10.10} | {self.duration:<8.1f} | {self.hints}"


class MatchingContentNotFound(Exception):
    pass

class NoFillerContentFound(Exception):
    pass

class ShowCatalog:
    _logger = logging.getLogger("MEDIA")
    supported_formats = ["mp4", "mpg", "mpeg", "avi", "mov", "mkv"]


    def __init__(self, config, rebuild_catalog=False, load=True, debug=False):
        self.config = config
        self._l = logging.getLogger(f"{self.config['network_name']}:CAT")

        self.clip_index = {}
        self.tags = []
        if rebuild_catalog:
            self.build_catalog()
        elif load:
            self.load_catalog()

    @staticmethod
    def _process_media(file_list, tag, hints=[]):
        ShowCatalog._logger.debug(f"_process_media starting processing for tag={tag} on {len(file_list)} files")
        show_clip_list = []
        #get the duration and path for each clip and add to the tag
        for fname in file_list:
            ShowCatalog._logger.debug(f"--_process_media is working on {fname}")
            # get video file length in seconds
            video_clip = VideoFileClip(fname)
            show_clip = ShowClip(fname, video_clip.duration, tag, hints)
            show_clip_list.append(show_clip)
            ShowCatalog._logger.debug(f"--_process_media is done with {fname}: {show_clip}")

        ShowCatalog._logger.debug(f"_process_media completed processing for tag={tag} on {len(file_list)} files")

        return show_clip_list


    @staticmethod
    def _find_media(path):
        ShowCatalog._logger.debug(f"_find_media scanning for media in {path}")
        file_list = []
        for ext in ShowCatalog.supported_formats:
            this_format = glob.glob(f"{path}/*.{ext}")
            file_list += this_format
            ShowCatalog._logger.debug(f"--Found {len(this_format)} files with {ext} extension - {len(file_list)} total found in {path} so far")

        ShowCatalog._logger.debug(f"_find_media done scanning {path} {len(file_list)}")
        return file_list

    @staticmethod
    def _process_hints(path):
        base = os.path.basename(path)
        hints = []
        if MonthHint.test_pattern(base):
            hints.append(MonthHint(base))
        if QuarterHint.test_pattern(base):
            hints.append(QuarterHint(base))
        if RangeHint.test_pattern(base):
            hints.append(RangeHint(base))

        return hints

    @staticmethod
    def _process_subs(dir_path, tag):
        subs = [ f.path for f in os.scandir(dir_path) if f.is_dir() ]
        clips = []
        for sub in subs:
            file_list = ShowCatalog._find_media(sub)
            hints = ShowCatalog._process_hints(sub)
            clips += ShowCatalog._process_media(file_list, tag, hints=hints)
        return clips

    def build_catalog(self):
        self._l.info(f"Starting catalog build for {self.config['network_name']}")
        #get the list of all tags
        tags = {}
        for day in DAYS:
            slots = self.config[day]
            for k in slots:
                if 'tags' in slots[k]:
                    tags[slots[k]['tags']] = True

        self.tags = list(tags.keys())

        #add commercial and bumps to the tags
        self.tags.append(self.config["commercial_dir"])
        self.tags.append(self.config["bump_dir"])
        total_count = 0

        #now populate each tag
        for tag in self.tags:
            self.clip_index[tag] = []
            self._l.info(f"Checking for media with tag={tag} in content folder")
            tag_dir = f"{self.config['content_dir']}/{tag}"
            file_list = ShowCatalog._find_media(tag_dir)

            self.clip_index[tag] = ShowCatalog._process_media(file_list, tag)
            self._l.info(f"--Found {len(self.clip_index[tag])} videos in {tag} folder")
            self._l.debug(f"---- {tag} media listing: {self.clip_index[tag]}")
            subdir_clips = ShowCatalog._process_subs(tag_dir, tag)
            self._l.info(f"--Found {len(subdir_clips)} videos in {tag} subfolders")
            self._l.debug(f"---- {tag} sub folder media listing: {subdir_clips}")
            self.clip_index[tag] += subdir_clips
            total_count += len(self.clip_index[tag])

        # add sign-off and off-air videos to the clip index
        if 'sign_off_video' in self.config:
            self._l.debug(f"Adding sign-off video")
            video_clip = VideoFileClip(self.config["sign_off_video"])
            self.clip_index['sign_off'] = ShowClip(self.config["sign_off_video"], video_clip.duration, 'sign_off')
            self._l.debug(f"Added sign-off video {self.config['sign_off_video']}")
            total_count+=1

        if "off_air_video" in self.config:
            self._l.debug(f"Adding off air video")
            video_clip = VideoFileClip(self.config["off_air_video"])
            self.clip_index['off_air'] = ShowClip(self.config["off_air_video"], video_clip.duration, 'off_air')
            self._l.debug(f"Added off air video {self.config['off_air_video']}")
            total_count+=1

        self._l.info(f"Catalog build complete. Added {total_count} clips to catalog.")
        with open(self.config['catalog_path'], 'wb') as f:
            pickle.dump(self.clip_index, f)

    def load_catalog(self):
        #takes a while, so check to see if it exists - build if not
        c_path = self.config['catalog_path']
        self._l.info("Loading catalog from file: " + c_path )
        if not os.path.isfile(c_path):
            self._l.warn("Catalog not found - starting new build")
            self.build_catalog()
        else:
            with open(c_path, "rb") as f:
                self.clip_index = pickle.load(f)
            self._l.info("Catalog written to file: " + c_path)

    def print_catalog(self):
        for tag in self.clip_index:
            #print("--------------------- " + tag + " ---------------------")
            if tag not in ['sign_off', 'off_air']:
                for item in self.clip_index[tag]:
                    print( item )

    def check_catalog(self):
        too_short = []
        for tag in self.clip_index:
            if tag not in ['sign_off', 'off_air']:
                for item in self.clip_index[tag]:
                    if item.duration < 1:
                        too_short.append(item)

        if len(too_short):
            print(f"{bcolors.FAIL}Found {len(too_short)} videos under 1 second in length:{bcolors.ENDC}")
            for v in too_short:
                print(f"{bcolors.WARNING}{v}{bcolors.ENDC}")
        else:
            print(f"{bcolors.OKGREEN}All checks passed{bcolors.ENDC}")




    def get_signoff(self):
        if 'sign_off' in self.clip_index:
            return self.clip_index['sign_off']
        return None

    def get_offair(self):
        if 'off_air' in self.clip_index:
            return self.clip_index['off_air']
        return None

    def _lowest_count(self, candidates):
        min_count = sys.maxsize
        lowest_matches = []
        for candidate in candidates:
            if candidate.count < min_count:
                min_count = candidate.count
                lowest_matches = [candidate]
            elif candidate.count == min_count:
                lowest_matches.append(candidate)

        return random.choice(lowest_matches)


    def _test_candidate_hints(hint_list, when):
        for hint in hint_list:
            if hint.hint(when) == False:
                return False
        return True

    def find_candidate(self, tag, seconds, when):
        if tag in self.clip_index and len(self.clip_index[tag]):
            candidates = self.clip_index[tag]
            matches = []
            for candidate in candidates:
                # restrict content to fit and be valid (zero duration is likely not valid)
                if candidate.duration < seconds and candidate.duration >= 1 and ShowCatalog._test_candidate_hints(candidate.hints, when):
                    matches.append(candidate)
            random.shuffle(matches)
            if not len(matches):
                err = f"Could not find candidate video for tag={tag} under {seconds} in len - maybe add some shorter content?"
                raise(MatchingContentNotFound(err))
            return self._lowest_count(matches)


    def find_filler(self, seconds, when):
        bump_tag = self.config['bump_dir']
        com_tag = self.config['commercial_dir']

        if not len(self.clip_index[bump_tag]) and not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler - add commercials and bumps...")
        return self.find_candidate(random.choice([bump_tag, com_tag, com_tag]), seconds, when)
