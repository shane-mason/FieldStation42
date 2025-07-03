import logging
import sys
import random
from fs42.catalog_entry import CatalogEntry, MatchingContentNotFound, NoFillerContentFound
from fs42.catalog_api import CatalogAPI
from fs42.timings import MIN_5, DAYS
from fs42.liquid_blocks import ReelBlock
from fs42.media_processor import MediaProcessor
from fs42.sequence_api import SequenceAPI


try:
    # try to import from version > 2.0
    from moviepy import VideoFileClip
except ImportError:
    # fall back to import from version 1.0
    from moviepy.editor import VideoFileClip  # type: ignore


FF_USE_FLUID_FILE_CACHE = True
FF_USE_CATAGLOG_DB = True


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class ShowCatalog:
    prebump = "prebump"
    postbump = "postbump"

    def __init__(self, config, rebuild_catalog=False, load=True, debug=False):
        self.config = config
        self._l = logging.getLogger(f"{self.config['network_name']}:CAT")

        # the main index for videos
        self.clip_index = {}

        # basically, a flattened list of clip_index keys
        self.tags = []

        self.__fluid_builder = None
        self.min_gap = 3
        if rebuild_catalog:
            self.build_catalog()
        elif load:
            self.load_catalog()

    def _write_catalog(self):
        # first, make them into a flat list
        flat_list = []

        for tag in self.clip_index:
            try:
                for entry in self.clip_index[tag]:
                    if isinstance(entry, CatalogEntry):
                        flat_list.append(entry)
                    else:
                        print(f"Warning: Entry {entry} on {tag} is not a CatalogEntry instance. Skipping.")

            except Exception as e:
                print(f"Error processing tag '{tag}': {e}")

        CatalogAPI.set_entries(self.config, flat_list)

    def load_catalog(self):
        if self.config["network_type"] == "streaming":
            return

        catalog_entries = CatalogAPI.get_entries(self.config)

        self.clip_index = {}

        for entry in catalog_entries:
            if entry.tag not in self.clip_index:
                self.clip_index[entry.tag] = []
            self.clip_index[entry.tag].append(entry)

    def build_catalog(self):
        self._l.info(f"Starting catalog build for {self.config['network_name']}")

        match self.config["network_type"]:
            case "standard":
                if FF_USE_FLUID_FILE_CACHE:
                    from fs42.fluid_builder import FluidBuilder

                    self.__fluid_builder = FluidBuilder()
                    self._l.info("Initializing fluid file cache...")
                    self.__fluid_builder.scan_file_cache(self.config["content_dir"])
                    self._l.info("Fluid file cache updated - continuing build")

                return self._build_standard()
            case "loop":
                return self._build_single()
            case "guide":
                raise NotImplementedError("Guide catalog not supported yet.")
            case "streaming":
                # just return for now
                return

    def _build_single(self, tag="content"):
        self.clip_index = {}
        self.tags = []
        # for station types with all files in a single directory
        self._l.info(f"Checking for media in {self.config['content_dir']} for single directory")
        file_list = MediaProcessor._find_media(self.config["content_dir"])
        self.clip_index[tag] = MediaProcessor._process_media(file_list, tag)
        self._l.info(f"Building complete - processed {len(file_list)} files")
        self._write_catalog()

    def _build_tags(self):
        self.tags = list(self.clip_index.keys())

    def _build_standard(self):
        self.clip_index = {}
        self.tags = []

        self._l.info("Standard network")
        start_bumps = {}
        end_bumps = {}

        # get the list of all tags
        tags = {}
        bump_overrides = {}
        commercial_overrides = {}
        for day in DAYS:
            slots = self.config[day]
            for k in slots:
                if "tags" in slots[k]:
                    if type(slots[k]["tags"]) is list:
                        for m in slots[k]["tags"]:
                            tags[m] = True
                    else:
                        tags[slots[k]["tags"]] = True

                    if "bump_dir" in slots[k]:
                        bump_overrides[slots[k]["bump_dir"]] = True
                    if "commercial_dir" in slots[k]:
                        commercial_overrides[slots[k]["commercial_dir"]] = True
                    if "start_bump" in slots[k]:
                        start_bumps[slots[k]["start_bump"]] = True
                    if "end_bump" in slots[k]:
                        end_bumps[slots[k]["end_bump"]] = True

        SequenceAPI.scan_sequences(self.config)

        self.clip_index["start_bumps"] = []
        self.clip_index["end_bumps"] = []

        # collect start and end bumps first
        for fp in start_bumps:
            path = f"{self.config['content_dir']}/{fp}"
            sb = MediaProcessor._process_media([path], "start_bumps", fluid=self.__fluid_builder)
            if len(sb) == 1:
                self.clip_index["start_bumps"].append(sb[0])
            else:
                self._l.error("Start bump specified but not found {fp}")
                self._l.error("File paths for start_bump should be relative to the content_dir")

        for fp in end_bumps:
            path = f"{self.config['content_dir']}/{fp}"
            eb = MediaProcessor._process_media([path], "end_bumps", fluid=self.__fluid_builder)
            if len(eb) == 1:
                self.clip_index["end_bumps"].append(eb[0])
            else:
                self._l.error("Start bump specified but not found {fp}")
                self._l.error("File paths for end_bump should be relative to the content_dir")

        # now inspect the tags and scan corresponding folders for media
        self.tags = list(tags.keys())
        # populate each tag
        total_count = 0
        for tag in self.tags:
            total_count += self._scan_directory(tag)

        # add commercial and bumps to the tags
        if "commercial_dir" in self.config:
            total_count += self._scan_directory(self.config["commercial_dir"])
        # setup the general bump dir
        if "bump_dir" in self.config and self.config["bump_dir"]:
            total_count += self._scan_directory(self.config["bump_dir"], is_bumps=True)

        for override_dir in bump_overrides:
            total_count += self._scan_directory(override_dir, is_bumps=True)

        for override_dir in commercial_overrides:
            total_count += self._scan_directory(override_dir)

        # add sign-off and off-air videos to the clip index
        if "sign_off_video" in self.config:
            self._l.debug("Adding sign-off video")
            video_clip = VideoFileClip(self.config["sign_off_video"])
            self.clip_index["sign_off"] = [CatalogEntry(self.config["sign_off_video"], video_clip.duration, "sign_off")]
            self._l.debug(f"Added sign-off video {self.config['sign_off_video']}")
            total_count += 1

        if "off_air_video" in self.config:
            self._l.debug("Adding off air video")
            video_clip = VideoFileClip(self.config["off_air_video"])
            self.clip_index["off_air"] = [CatalogEntry(self.config["off_air_video"], video_clip.duration, "off_air")]
            self._l.debug(f"Added off air video {self.config['off_air_video']}")
            total_count += 1

        if "off_air_image" in self.config:
            self._l.debug("Adding offair image")
            self.clip_index["off_air_image"] = CatalogEntry(self.config["off_air_image"], MIN_5, "off_air")
            self._l.debug(f"Added off air image {self.config['off_air_image']}")
            total_count += 1

        self._l.info(f"Catalog build complete. Added {total_count} clips to catalog.")
        self._build_tags()
        self._write_catalog()

    def _scan_directory(self, tag, is_bumps=False):
        count_added = 0
        if tag not in self.clip_index:
            self.clip_index[tag] = []
            self._l.info(f"Checking for media with tag={tag} in content folder")
            tag_dir = f"{self.config['content_dir']}/{tag}"
            file_list = MediaProcessor._find_media(tag_dir)

            self.clip_index[tag] = MediaProcessor._process_media(file_list, tag, fluid=self.__fluid_builder)
            self._l.info(f"--Found {len(self.clip_index[tag])} videos in {tag} folder")
            self._l.debug(f"---- {tag} media listing: {self.clip_index[tag]}")

            subdir_clips = MediaProcessor._process_subs(tag_dir, tag, bumpdir=is_bumps, fluid=self.__fluid_builder)

            self._l.info(f"--Found {len(subdir_clips)} videos in {tag} subfolders")
            self._l.debug(f"---- {tag} sub folder media listing: {subdir_clips}")

            if is_bumps:
                pre_key = f"{tag}-{ShowCatalog.prebump}"
                post_key = f"{tag}-{ShowCatalog.postbump}"
                (pre, fill, post) = MediaProcessor._by_position(subdir_clips, ShowCatalog.prebump, ShowCatalog.postbump)
                self.clip_index[tag] = self.clip_index[tag] + fill
                self.clip_index[pre_key] = pre
                self.clip_index[post_key] = post
                count_added += len(pre) + len(fill) + len(post)
            else:
                self.clip_index[tag] += subdir_clips
                count_added += len(self.clip_index[tag])
        return count_added

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
            if tag not in ["sign_off", "off_air"]:
                for item in self.clip_index[tag]:
                    if hasattr(item, "duration") and item.duration < 1:
                        too_short.append(item)

        if len(too_short):
            print(f"{bcolors.FAIL}Found {len(too_short)} videos under 1 second in length:{bcolors.ENDC}")
            for v in too_short:
                print(f"{bcolors.WARNING}{v}{bcolors.ENDC}")
        else:
            print(f"{bcolors.OKGREEN}All checks passed{bcolors.ENDC}")

    def get_signoff(self):
        if "sign_off" in self.clip_index:
            return self.clip_index["sign_off"]
        return None

    def get_offair(self):
        all_offair = CatalogAPI.get_by_tag(self.config, "off_air")
        candidate = None
        if all_offair and len(all_offair):
            candidate = all_offair[0]
        return candidate

    def get_start_bump(self, fp):
        if fp in self.clip_index["start_bumps"]:
            return self.clip_index["start_bumps"][fp]
        return None

    def get_end_bump(self, fp):
        if fp in self.clip_index["end_bumps"]:
            return self.clip_index["end_bumps"][fp]
        return None

    def entry_by_fpath(self, fpath):
        results = CatalogAPI.get_by_path(self.config, fpath)
        return results

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
                if (
                    candidate.duration < seconds
                    and candidate.duration >= 1
                    and MediaProcessor._test_candidate_hints(candidate.hints, when)
                ):
                    matches.append(candidate)
            random.shuffle(matches)
            if not len(matches):
                err = f"Could not find candidate video for tag={tag} under {seconds} in len - maybe add some shorter content?"
                raise (MatchingContentNotFound(err))
            result = self._lowest_count(matches)
            # note, this has been migrated
            result.count += 1
            # CatalogAPI.set_play_count(self.config, result.path, result.count)
            return result

    def find_filler(self, seconds, when):
        bump_tag = self.config["bump_dir"]
        com_tag = self.config["commercial_dir"]

        if not len(self.clip_index[bump_tag]) and not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler - add commercials and bumps...")
        return self.find_candidate(random.choice([bump_tag, com_tag, com_tag]), seconds, when)

    def find_bump(self, seconds, when, position=None, bump_tag=None):
        if not bump_tag:
            bump_tag = self.config["bump_dir"]

        if not len(self.clip_index[bump_tag]):
            raise NoFillerContentFound("Can't find filler - add bumps...")

        if position:
            pre_key = f"{bump_tag}-{ShowCatalog.prebump}"
            post_key = f"{bump_tag}-{ShowCatalog.postbump}"
            if position == ShowCatalog.prebump and pre_key in self.clip_index and len(self.clip_index[pre_key]):
                return self.find_candidate(pre_key, seconds, when)
            elif position == ShowCatalog.postbump and post_key in self.clip_index and len(self.clip_index[post_key]):
                return self.find_candidate(post_key, seconds, when)
            else:
                # then none were specified, so use regular bumps
                return self.find_candidate(bump_tag, seconds, when)
        else:
            return self.find_candidate(bump_tag, seconds, when)

    def find_commercial(self, seconds, when, commercial_dir):
        com_tag = commercial_dir if commercial_dir else self.config["commercial_dir"]

        if not len(self.clip_index[com_tag]):
            raise NoFillerContentFound(f"Can't find filler content in {com_tag} - please add commercials.")
        return self.find_candidate(com_tag, seconds, when)

    # makes blocks of reels in bump-commercial-commercial-bump format
    def make_reel_block(self, when, bumpers=True, target_duration=120, commercial_dir=None, bump_dir=None):
        reels = []
        remaining = target_duration
        start_candidate = None
        end_candidate = None

        if bumpers:
            start_candidate = self.find_bump(target_duration, when, ShowCatalog.prebump, bump_tag=bump_dir)
            end_candidate = self.find_bump(target_duration, when, ShowCatalog.postbump, bump_tag=bump_dir)

            remaining -= start_candidate.duration
            remaining -= end_candidate.duration

        # aim for lower and should average close over time since the returned can be larger
        while remaining > (target_duration * 0.1):
            if not self.config["commercial_free"]:
                candidate = self.find_commercial(target_duration, when, commercial_dir)
            else:
                candidate = self.find_bump(target_duration, when, None, bump_dir)
            remaining -= candidate.duration
            reels.append(candidate)

        return ReelBlock(start_candidate, reels, end_candidate)

    def make_reel_fill(self, when, length, use_bumpers=True, commercial_dir=None, bump_dir=None, strict_count=None):
        target_break_duration = self.config["break_duration"]

        if strict_count:
            target_break_duration = length / strict_count

        remaining = length
        blocks = []
        keep_going = True
        while remaining and keep_going:
            block = None
            try:
                block = self.make_reel_block(
                    when, use_bumpers, target_break_duration, commercial_dir=commercial_dir, bump_dir=bump_dir
                )
            except MatchingContentNotFound:
                self._l.debug(
                    f"Could not find matching content for {remaining} seconds - will attempt to fill with BRB"
                )

            if block and (remaining - block.duration) > 0:
                remaining -= block.duration
                blocks.append(block)

                if strict_count and len(blocks) >= strict_count:
                    keep_going = False

            else:
                keep_going = False

        keep_going = True

        # discard that block and fill using the tightest technique possible
        additional_reels = []

        while remaining and keep_going:
            candidate = None
            try:
                if not self.config["commercial_free"]:
                    candidate = self.find_commercial(seconds=remaining, when=when, commercial_dir=commercial_dir)
                else:
                    candidate = self.find_bump(remaining, when, "fill")
            except MatchingContentNotFound:
                if remaining > self.min_gap:
                    self._l.debug(
                        f"Could not find matching content for {remaining} seconds - will attempt to fill with BRB"
                    )

            if candidate:
                additional_reels.append(candidate)
                remaining -= candidate.duration
            else:
                # If BRB is enabled, we'll use that to fill the remaining gap
                if remaining > self.min_gap and "be_right_back_media" in self.config:
                    brb = CatalogEntry(self.config["be_right_back_media"], duration=remaining, tag="brb")
                    additional_reels.append(brb)
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
                current_duration += candidate.duration
                clips.append(candidate)
            except MatchingContentNotFound as e:
                if len(clips) == 0:
                    # then there isn't any valid content at all.
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
            if type(self.clip_index[tag]) is list:
                count += len(self.clip_index[tag])
            else:
                count += 1
        return (len(self.tags), count)
