import logging
import pickle
import sys
import random
from fs42.timings import MIN_5, DAYS
from fs42.catalog_entry import CatalogEntry, MatchingContentNotFound, NoFillerContentFound
from fs42.liquid_blocks import ReelBlock
from fs42.media_processor import MediaProcessor
from fs42.series import SeriesIndex

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
        


class ShowCatalog:
    prebump = "prebump"
    postbump = "postbump"

    def __init__(self, config, rebuild_catalog=False, load=True, debug=False):
        self.config = config
        self._l = logging.getLogger(f"{self.config['network_name']}:CAT")
        
        # the main index for videos
        self.clip_index = {}
        # stores sequences (series) and their play-state
        self.sequences = {}
        # basically, a flattened list of clip_index keys
        self.tags = []

        if rebuild_catalog:
            self.build_catalog()
        elif load:
            self.load_catalog()

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
        file_list = MediaProcessor._find_media(self.config['content_dir'])
        self.clip_index[tag] = MediaProcessor._process_media(file_list, tag)
        self._l.info(f"Building complete - processed {len(self.config['content_dir'])} files")
        self._write_catalog()

    def _build_tags(self):
        self.tags = list(self.clip_index.keys())

    def _build_standard(self):
        self.clip_index = {}
        #self.sequences = {}
        self.tags = []

        self._l.info(f"Standard network")
        start_bumps = {}
        end_bumps = {}

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

                    if 'start_bump' in slots[k]:
                        start_bumps[slots[k]['start_bump']] = True
                    if 'end_bump' in slots[k]:
                        end_bumps[slots[k]['end_bump']] = True

        self.scan_sequences()

        self.clip_index["start_bumps"] = {}
        self.clip_index["end_bumps"] = {}

        #collect start and end bumps first
        for fp in start_bumps:
            path = f"{self.config['content_dir']}/{fp}"
            sb = MediaProcessor._process_media([path], "start_bumps")
            if len(sb) == 1:
                self.clip_index["start_bumps"][fp] = sb[0]
            else:
                self._l.error("Start bump specified but not found {fp}")
                self._l.error("File paths for start_bump should be relative to the content_dir")

        for fp in end_bumps:
            path = f"{self.config['content_dir']}/{fp}"
            eb = MediaProcessor._process_media([path], "end_bumps")
            if len(sb) == 1:
                self.clip_index["end_bumps"][fp] = eb[0]
            else:
                self._l.error("Start bump specified but not found {fp}")
                self._l.error("File paths for end_bump should be relative to the content_dir")

        # now inspect the tags and scan corresponding folders for media
        self.tags = list(tags.keys())

        #add commercial and bumps to the tags
        if "commercial_dir" in self.config:
            self.tags.append(self.config["commercial_dir"])
        if "bump_dir" in self.config:
            self.tags.append(self.config["bump_dir"])

        total_count = 0

        #now populate each tag
        for tag in self.tags:
            self.clip_index[tag] = []

            self._l.info(f"Checking for media with tag={tag} in content folder")
            tag_dir = f"{self.config['content_dir']}/{tag}"
            file_list = MediaProcessor._find_media(tag_dir)

            self.clip_index[tag] = MediaProcessor._process_media(file_list, tag)
            self._l.info(f"--Found {len(self.clip_index[tag])} videos in {tag} folder")
            self._l.debug(f"---- {tag} media listing: {self.clip_index[tag]}")
            subdir_clips = MediaProcessor._process_subs(tag_dir, tag, bumpdir=(tag==self.config["bump_dir"]))
            self._l.info(f"--Found {len(subdir_clips)} videos in {tag} subfolders")
            self._l.debug(f"---- {tag} sub folder media listing: {subdir_clips}")
            
            if( tag == self.config["bump_dir"]):
                (pre, fill, post) = MediaProcessor._by_position(subdir_clips, ShowCatalog.prebump, ShowCatalog.postbump)
                self.clip_index[tag] = self.clip_index[tag] + fill
                self.clip_index[ShowCatalog.prebump] = pre
                self.clip_index[ShowCatalog.postbump] = post
                total_count += len(pre) + len(fill) + len(post)
            else:                
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
        self._build_tags()
        #print(self.tags)
        self._write_catalog()

    def _write_catalog(self):
        with open(self.config['catalog_path'], 'wb') as f:
            cat_out = {
                'version': 0.1,
                'clip_index': self.clip_index,
                'sequences': self.sequences
            }
            pickle.dump(cat_out, f)

    def rebuild_sequences(self, commit=False):
        self.sequences = {}
        self.scan_sequences()
        if commit:
            self._write_catalog()

    def scan_sequences(self, commit=False):

        for day in DAYS:
            slots = self.config[day]
            for k in slots:

                if 'sequence' in slots[k]:
                    # the user supplied sequence name
                    seq_name = slots[k]['sequence']
                    seq_key = ""
                    to_add = []
                    if  isinstance(slots[k]['tags'], list):
                        to_add += slots[k]['tags']
                    else:
                        to_add.append(slots[k]['tags'])


                    for seq_tag in to_add:
                        if seq_tag in self.config['clip_shows']:
                            self._l.error(f"Schedule logic error in {self.config['network_name']}: Clip shows are not currently supported as sequences")
                            self._l.error(f"{seq_tag} is in the clip shows list, but is declared as a sequence on {day} in slot {k}")
                            exit(-1)
                        seq_key = SeriesIndex.make_key(seq_tag,seq_name)
                        if seq_key not in self.sequences:
                            self._l.info(f"Adding sequence {seq_key}")
                            series = SeriesIndex(seq_tag)
                            file_list = MediaProcessor._rfind_media(f"{self.config['content_dir']}/{seq_tag}")
                            series.populate(file_list)
                            self.sequences[seq_key] = series
        if commit:
            self._write_catalog()

    def load_catalog(self):
        #takes a while, so check to see if it exists - build if not
        c_path = self.config['catalog_path']
        self._l.debug("Loading catalog from file: " + c_path )

            
        with open(c_path, "rb") as f:
            try:
                cat_in = pickle.load(f)
                #make sure this is a modern version of the catalog
                if 'version' in cat_in:
                    self.clip_index = cat_in['clip_index']
                    self.sequences = cat_in['sequences']
                else:
                    self.clip_index = cat_in
                    self.sequences = {}
                self._build_tags()
            except AttributeError as e:
                # print error message in red
                print('\033[91m' + "Error loading catalogs - this means you probably need to update your catalog format")
                print("Please rebuild catalogs by running station_42.py --rebuild_catalog" + '\033[0m')
                sys.exit(-1)

            self._l.debug("Catalog read read from file " + c_path)
        

    def get_text_listing(self):
        content = "TITLE                | TAG        | Duration  | Hints\n"
        for tag in self.clip_index:
            if tag not in ["sign_off", "off_air"]:
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
        if 'off_air_image' in self.clip_index:
            return self.clip_index['off_air_image']
        return None

    def get_start_bump(self, fp):
        if fp in self.clip_index['start_bumps']:
            return self.clip_index['start_bumps'][fp]
        return None
    
    def get_end_bump(self, fp):
        if fp in self.clip_index['end_bumps']:
            return self.clip_index['end_bumps'][fp]
        return None

    def get_next_in_sequence(self, sequence_key):
        if sequence_key not in self.sequences:
            self._l.error("Sequence specified but could not find - please check your configuration and rebuild the catalog.")
            exit(-1)
        
        episode = self.sequences[sequence_key].get_next()
        entry:CatalogEntry = self._by_fpath(episode)
        return entry
        

    def _by_fpath(self, fpath):
        for tag in self.clip_index:
            try:
                for item in self.clip_index[tag]:
                    if type(item) is CatalogEntry:
                
                        if item.path == fpath:
                            return item
            except TypeError as te:
                pass

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
                if candidate.duration < seconds and candidate.duration >= 1 and MediaProcessor._test_candidate_hints(candidate.hints, when):
                    matches.append(candidate)
            random.shuffle(matches)
            if not len(matches):
                err = f"Could not find candidate video for tag={tag} under {seconds} in len - maybe add some shorter content?"
                raise(MatchingContentNotFound(err))
            result = self._lowest_count(matches)
            result.count += 1
            return result

    def find_filler(self, seconds, when):
        bump_tag = self.config['bump_dir']
        com_tag = self.config['commercial_dir']

        if not len(self.clip_index[bump_tag]) and not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler - add commercials and bumps...")
        return self.find_candidate(random.choice([bump_tag, com_tag, com_tag]), seconds, when)


    def find_bump(self, seconds, when, position=None):
        bump_tag = self.config['bump_dir']
        
        if not len(self.clip_index[bump_tag]):
            raise NoFillerContentFound("Can't find filler - add bumps...")
        
        if position:
            if position == ShowCatalog.prebump and len(self.clip_index[ShowCatalog.prebump]):
                return self.find_candidate(ShowCatalog.prebump, seconds, when)
            elif position == ShowCatalog.postbump and len(self.clip_index[ShowCatalog.postbump]):
                return self.find_candidate(ShowCatalog.postbump, seconds, when)
            else:
               #then none were specified, so use regular bumps
               return self.find_candidate(bump_tag, seconds, when) 
        else:
            return self.find_candidate(bump_tag, seconds, when)

    def find_commercial(self, seconds, when):
        com_tag = self.config['commercial_dir']

        if not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler - add commercials...")
        return self.find_candidate(com_tag, seconds, when)                

    #makes blocks of reels in bump-commercial-commercial-bump format
    def make_reel_block(self, when,  bumpers=True, target_duration=120):
        reels = []
        remaining = target_duration
        start_candidate = None
        end_candidate = None
        if bumpers:
            start_candidate = self.find_bump(target_duration, when, ShowCatalog.prebump)
            end_candidate = self.find_bump(target_duration, when, ShowCatalog.postbump)

            remaining -= start_candidate.duration
            remaining -= end_candidate.duration
            
        
        #aim for lower and should average close over time since the returned can be larger
        while remaining > (target_duration *.1):
            
            if self.config['commercial_free'] == False:
                candidate = self.find_commercial(target_duration, when)
            else:
                candidate = self.find_bump(target_duration, when)
            remaining -= candidate.duration
            reels.append(candidate)
        
        return ReelBlock(start_candidate, reels, end_candidate)

    def make_reel_fill(self, when, length, bumpers=True):
        remaining = length
        blocks = []
        while remaining:
            block = self.make_reel_block(when, bumpers, self.config['break_duration'])
            
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
                            candidate = self.find_bump(remaining, when, "fill")
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
                # if it is a small or negative number, this will throw an exception when a candidate isn't found
                candidate = self.find_candidate(tag, duration - current_duration, when)
                current_duration+=candidate.duration
                clips.append(candidate)
            except MatchingContentNotFound as e:
                if len(clips) == 0:
                    #then there isn't any valid content at all.
                    raise e
                # then there are no more clips, so exit the loop
                keep_going = False
        return clips

    def summary(self):
        (tags, count) = self.summary_data()
        text = f"{count} videos under {tags} tags"
        return text

    def summary_data(self):
        count = 0
        for tag in self.tags:
            #print(self.clip_index[tag])
            if type(self.clip_index[tag]) is list:
                count += len(self.clip_index[tag])
            else:
                count += 1
        return (len(self.tags), count)        


                    
                

