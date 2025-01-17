import os
import glob
import logging
import pickle
import sys
import random
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint
from fs42.liquid_blocks import ReelBlock

try:
    #try to import from version > 2.0
    from moviepy import VideoFileClip
except ImportError: 
    #fall back to import from version 1.0
    from moviepy.editor import VideoFileClip # type: ignore

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

class CatalogEntry:
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
            show_clip = CatalogEntry(fname, video_clip.duration, tag, hints)
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

        match self.config["network_type"]:
            case "standard":
                return self._build_standard()
            case "loop":
                return self._build_single()
            case "guide":
                raise NotImplementedError("Guide catalog not supported yet.")
    
    def _build_single(self, tag="content"):
        self.clip_index = {}
        self.tags = []
        #for station types with all files in a single directory
        self._l.info(f"Checking for media in {self.config['content_dir']} for single directory")
        file_list = ShowCatalog._find_media(self.config['content_dir'])
        self.clip_index[tag] = ShowCatalog._process_media(file_list, tag)
        self._l.info(f"Building complete - processed {len(self.config['content_dir'])} files")
        self._write_catalog()

    def _build_tags(self):
        self.tags = list(self.clip_index.keys())

    def _build_standard(self):
        self.clip_index = {}
        self.tags = []

        self._l.info(f"Standard network")
       #get the list of all tags
        tags = {}
        for day in DAYS:
            slots = self.config[day]
            for k in slots:
                if 'tags' in slots[k]:
                    if type(slots[k]['tags']) is list:
                        for l in slots[k]['tags']:
                            tags[l] = True
                    else:
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
            self.clip_index['sign_off'] = CatalogEntry(self.config["sign_off_video"], video_clip.duration, 'sign_off')
            self._l.debug(f"Added sign-off video {self.config['sign_off_video']}")
            total_count+=1

        if "off_air_video" in self.config:
            self._l.debug(f"Adding off air video")
            video_clip = VideoFileClip(self.config["off_air_video"])
            self.clip_index['off_air'] = CatalogEntry(self.config["off_air_video"], video_clip.duration, 'off_air')
            self._l.debug(f"Added off air video {self.config['off_air_video']}")
            total_count+=1

        if "off_air_image" in self.config:
            self._l.debug(f"Adding offair image")
            self.clip_index['off_air_image'] = CatalogEntry(self.config['off_air_image'], MIN_5, 'off_air')
            self._l.debug(f"Added off air image {self.config['off_air_image']}")
            total_count+=1

        self._l.info(f"Catalog build complete. Added {total_count} clips to catalog.")
        self._write_catalog()

    def _write_catalog(self):
        with open(self.config['catalog_path'], 'wb') as f:
            pickle.dump(self.clip_index, f)

    def load_catalog(self):
        #takes a while, so check to see if it exists - build if not
        c_path = self.config['catalog_path']
        self._l.info("Loading catalog from file: " + c_path )
        if False: #not os.path.isfile(c_path):
            self._l.warning("Catalog not found - starting new build")
            self.build_catalog()
        else:
            
            with open(c_path, "rb") as f:
                try:
                    self.clip_index = pickle.load(f)
                    self._build_tags()
                except AttributeError as e:
                    # print error message in red
                    print('\033[91m' + "Error loading catalogs - this means you probably need to update your catalog format")
                    print("Please rebuild catalogs by running station_42.py -x. Cheers!" + '\033[0m')
                    sys.exit(-1)

            self._l.info("Catalog read read from file " + c_path)
        print("Loaded catatlog")

    def get_text_listing(self):
        content = "TITLE                | TAG        | Duration    | Hints\n"
        for tag in self.clip_index:
            if tag not in ['sign_off', 'off_air']:
                for item in self.clip_index[tag]:
                    content += f"{str(item)}\n"
        return content

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
        if 'off_air_image' in self.clip_index['off_air_image']:
            return self.clip_index['off_air_image']
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

    def get_all_by_tag(self, tag):
        if tag in self.clip_index and len(self.clip_index[tag]):
            return self.clip_index[tag]
        else:
            return None
        
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

    def find_bump(self, seconds, when):
        bump_tag = self.config['bump_dir']

        if not len(self.clip_index[bump_tag]):
            raise NoFillerContentFound("Can't find filler - add bumps...")
        return self.find_candidate(bump_tag, seconds, when)

    def find_commercial(self, seconds, when):
        com_tag = self.config['commercial_dir']

        if not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler - add commercials...")
        return self.find_candidate(com_tag, seconds, when)                

    #makes blocks of reels in bump-commercial-commercial-bump format
    def make_reel_block(self, when,  bumpers=True, max_bumper_duration=120, max_commercial_duration=120, target_duration=120):
        reels = []
        remaining = target_duration
        start_candidate = None
        end_candidate = None
        if bumpers:
            start_candidate = self.find_bump(max_bumper_duration, when)
            end_candidate = self.find_bump(max_bumper_duration, when)
            remaining -= start_candidate.duration
            remaining -= end_candidate.duration
            
        
        #aim for lower and should average close over time
        while remaining > (target_duration *.1):
            if self.config['commercial_free'] == False:
                candidate = self.find_commercial(max_commercial_duration, when)
            else:
                candidate = self.find_bump(max_commercial_duration, when)
            remaining -= candidate.duration
            reels.append(candidate)
        
        return ReelBlock(start_candidate, reels, end_candidate)

    def make_reel_fill(self, when, length, bumpers=True):
        remaining = length
        blocks = []
        while remaining:
            block = self.make_reel_block(when, bumpers)
            
            if (remaining - block.duration) > 0:
                remaining -= block.duration
                blocks.append(block)
            else:
                #discard that block and fill using the tightest technique possible
                keep_going = True
                additional_reels = []
                while remaining and keep_going:
                    candidate = None
                    
                    try:
                        if self.config["commercial_free"] == False:
                            candidate = self.find_commercial(remaining, when)
                        else:
                            candidate = self.find_bump(remaining, when)
                    except:
                        pass

                    if candidate is not None:
                        additional_reels.append(candidate)
                        remaining-=candidate.duration
                    else:
                        keep_going = False
                        remaining = 0

                blocks.append(ReelBlock(None, additional_reels, None))

        return blocks
        
    def gather_clip_content(self, tag, duration, when):
        current_duration = 0
        keep_going = True
        clips = []
        while keep_going:
            try:
                candidate = self.find_candidate(tag, duration - current_duration, when)
                current_duration+=candidate.duration
                clips.append(candidate)
            except MatchingContentNotFound as e:
                if len(clips) == 0:
                    #then there isn't any valid content at all.
                    raise e
                keep_going = False
        return clips

    def summary(self):
        count = 0
        print(f"Getting summary {self.tags}")
        for tag in self.tags:
            #print(self.clip_index[tag])
            if type(self.clip_index[tag]) is list:
                count += len(self.clip_index[tag])
            else:
                count += 1
        text = f"Tag count: {len(self.tags)}  Video count: {count}"
        return text



                    
                

