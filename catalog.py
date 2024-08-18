import os
import glob
import logging
import pickle
import sys
import random
from timings import *
from moviepy.editor import VideoFileClip, concatenate_videoclips

class ShowClip:
    def __init__(self, path, duration, tag):
        self.path = path
        #get the show name from the path
        self.title = os.path.basename(path).split(".")[0]
        self.duration = duration
        self.tag = tag
        self.count = 0

    def __str__(self):
        return f"{self.title} - {self.tag} -{self.duration}"


class ShowCatalog:

    def __init__(self, config):
        self.config = config
        self._l = logging.getLogger(f"{self.config['network_name']}:CAT")
        self.tag_index = {}
        self.tags = []
        self.load_catalog()


    def build_catalog(self):
        print("Building catalog...")
        #get the list of all tags
        tags = {}
        for day in DAYS:
            slots = self.config[day]
            for k in slots:
                tags[slots[k]['tags']] = True

        self.tags = list(tags.keys())

        #add commercial and bumps to the tags
        self.tags.append(self.config["commercial_dir"])
        self.tags.append(self.config["bump_dir"])

        #now populate each tag
        for tag in self.tags:
            self._l.info("Evaluating tag: " + tag)
            file_list = glob.glob(self.config['content_dir'] + "/" + tag + "/*.mp4")
            show_clip_list = []
            #get the duration and path for each clip and add to the tag
            for fname in file_list:
                # get video file length in seconds
                try:
                    video_clip = VideoFileClip(fname)
                    self._l.info("Adding clip: " + fname )
                    show_clip = ShowClip(fname, video_clip.duration, tag)
                    show_clip_list.append(show_clip)
                except:
                    self._l.error("Error processing video...")
                    raise Exception(f"Error processing video {f}")

            self.tag_index[tag] = show_clip_list


        with open(self.config['catalog_path'], 'wb') as f:
            pickle.dump(self.tag_index, f)

    def load_catalog(self):
        #takes a while, so check to see if it exists - build if not
        c_path = self.config['catalog_path']
        self._l.info("Loading catalog from file: " + c_path )
        if not os.path.isfile(c_path):
            self._l.warn("Catalog not found - starting new build")
            self.build_catalog()
        else:
            with open(c_path, "rb") as f:
                self.tag_index = pickle.load(f)
            self._l.info("Catalog written to file: " + c_path)

    def print_catalog(self):
        for tag in self.tag_index:
            print("----------- " + tag + " -----------")
            for item in self.tag_index[tag]:
                print( item )



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


    def find_candidate(self, tag, seconds):
        if tag in self.tag_index and len(self.tag_index[tag]):
            candidates = self.tag_index[tag]
            matches = []
            for candidate in candidates:
                if candidate.duration < seconds:
                    matches.append(candidate)
            random.shuffle(matches)
            if not len(matches):
                print("Couldnt find it")
                print(tag)
                print(seconds)
                raise(Exception())
            return self._lowest_count(matches)


    def find_filler(self, seconds):
        bump_tag = self.config['bump_dir']
        com_tag = self.config['commercial_dir']

        if not len(self.tag_index[bump_tag]) and not len(self.tag_index[com_tag]):
            raise Exception("Can't find filler - add commercials and bumps...")
        return self.find_candidate(random.choice([bump_tag, com_tag, com_tag]), seconds)
