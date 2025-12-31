import logging
import os
import glob
import json
import ffmpeg
from fs42.fluid_objects import FileRepoEntry
from fs42 import timings

try:
    # try to import from version > 2.0
    from moviepy import VideoFileClip
except ImportError:
    # fall back to import from version 1.0
    from moviepy.editor import VideoFileClip  # type: ignore

try:
    import mutagen
except ImportError:
    mutagen = None

from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint, BumpHint, DayPartHint
from fs42.catalog_entry import CatalogEntry


class MediaProcessor:
    # Define media type extensions
    VIDEO_FORMATS = ["mp4", "mpg", "mpeg", "avi", "mov", "mkv", "ts", "m4v", "webm", "wmv"]
    AUDIO_FORMATS = ["mp3", "m4a", "flac", "wav", "aac", "ogg", "opus", "wma"]

    # For backward compatibility, default to all formats
    supported_formats = VIDEO_FORMATS + AUDIO_FORMATS

    @staticmethod
    def get_media_type(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        if ext in MediaProcessor.AUDIO_FORMATS:
            return 'audio'
        else:
            return 'video'

    @staticmethod
    def extract_audio_metadata(file_path: str) -> dict:
        if mutagen is None:
            logging.getLogger("MEDIA").warning("mutagen library not available, skipping audio metadata extraction")
            return {}

        try:
            audio = mutagen.File(file_path)
            if audio is None:
                return {}

            metadata = {}

            # Extract common tags - mutagen returns lists for most values
            if hasattr(audio, 'tags') and audio.tags:
                # Map of ID3v2 frame names to our simple tag names
                # Different formats use different tag names:
                # MP3 uses ID3v2 (TIT2, TPE1, etc)
                # MP4/M4A uses \xa9nam, \xa9ART, etc
                # FLAC/OGG use vorbis comments (title, artist, etc)
                tag_mappings = {
                    'title': ['TIT2', 'title', '\xa9nam'],
                    'artist': ['TPE1', 'artist', '\xa9ART'],
                    'album': ['TALB', 'album', '\xa9alb'],
                    'date': ['TDRC', 'date', '\xa9day', 'year'],
                    'genre': ['TCON', 'genre', '\xa9gen']
                }

                for tag_name, possible_keys in tag_mappings.items():
                    for key in possible_keys:
                        value = audio.tags.get(key)
                        if value:
                            # Convert to string, handle list values
                            if isinstance(value, list) and len(value) > 0:
                                metadata[tag_name] = str(value[0])
                            else:
                                metadata[tag_name] = str(value)
                            break  # Found it, move to next tag

            # Fallback to filename if no title
            if 'title' not in metadata:
                metadata['title'] = os.path.splitext(os.path.basename(file_path))[0]

            return metadata

        except Exception as e:
            logging.getLogger("MEDIA").debug(f"Could not extract metadata from {file_path}: {e}")
            # Return basic metadata from filename
            return {
                'title': os.path.splitext(os.path.basename(file_path))[0]
            }

    def process_one(fname, tag, hints, fluid=None, content_type="feature") -> CatalogEntry:
        _l = logging.getLogger("MEDIA")
        _l.debug(f"--process_one is working on {fname}")
        # get video file length in seconds
        duration = 0.0
        result = None
        try:
            full_path = False
            if fluid:
                full_path = os.path.realpath(fname)
                cached = fluid.check_file_cache(full_path)
                if cached:
                    duration = cached.duration

            if not duration:
                # then do the processing
                duration = MediaProcessor._get_duration(fname)

            # it might not support streams, so check with moviepy
            if duration <= 0.0:
                try:
                    video_clip = VideoFileClip(fname)
                    duration = video_clip.duration
                except Exception as e:
                    _l.error(f"Error in moviepy attempting to get duration for {fname}")
                    _l.exception(e)
            # see if both returned 0
            if duration <= 0.0:
                _l.warning(f"Could not get a duration for tag: {tag}  file: {fname}")
                _l.warning("Files with 0 length can't be added to the catalog.")
            else:
                # Detect media type from file extension
                media_type = MediaProcessor.get_media_type(fname)
                show_clip = CatalogEntry(fname, duration, tag, hints, content_type=content_type, media_type=media_type)
                result = show_clip
                result.realpath = full_path
                _l.debug(f"--_process_media is done with {fname}: {show_clip}")

        except Exception as e:
            _l.exception(e)
            _l.error(f"Error processing media file {fname}")

        return result

    @staticmethod
    def _process_media(file_list, tag, hints=[], fluid=None, content_type="feature") -> list[CatalogEntry]:
        _l = logging.getLogger("MEDIA")
        _l.debug(f"_process_media starting processing for tag={tag} on {len(file_list)} files")
        show_clip_list = []

        # collect list of files that fail
        failed = []

        # get the duration and path for each clip and add to the tag
        for fname in file_list:
            _l.debug(f"--_process_media is working on {fname}")
            # get video file length in seconds
            results = MediaProcessor.process_one(fname, tag, hints, fluid, content_type)
            if results:
                show_clip_list.append(results)
            else:
                failed.append(failed)

        _l.debug(f"_process_media completed processing for tag={tag} on {len(file_list)} files")

        if len(failed):
            _l.warning(f"Errors were encountered during processing - error count: {len(failed)}")
            count_printed = 0
            for f in failed:
                _l.warning(f)
                count_printed += 1
                if count_printed >= 10:
                    _l.warning(f"and {len(failed) - count_printed} more...")

        return show_clip_list

    @staticmethod
    def _get_duration(file_name) -> float:
        probed = ffmpeg.probe(file_name)

        if "streams" in probed and len(probed["streams"]) and "duration" in probed["streams"][0]:
            return float(probed["streams"][0]["duration"])
        elif "format" in probed and "duration" in probed["format"]:
            return float(probed['format']['duration'])
        else:
            return -1

    @staticmethod
    def _find_media(path, media_filter="video") -> list[str]:
        logging.getLogger("MEDIA").debug(f"_find_media scanning for media in {path} with filter={media_filter}")

        # Determine which formats to scan based on filter
        if media_filter == "audio":
            formats_to_scan = MediaProcessor.AUDIO_FORMATS
        elif media_filter == "video":
            formats_to_scan = MediaProcessor.VIDEO_FORMATS
        else:  # "mixed"
            formats_to_scan = MediaProcessor.supported_formats

        file_list = []
        for ext in formats_to_scan:
            this_format = glob.glob(f"{path}/*.{ext}")
            file_list += this_format
            logging.getLogger("MEDIA").debug(
                f"--Found {len(this_format)} files with {ext} extension - {len(file_list)} total found in {path} so far"
            )

        logging.getLogger("MEDIA").debug(f"_find_media done scanning {path} {len(file_list)}")
        return file_list

    @staticmethod
    def rich_find_media(path: str, media_filter="video") -> list[FileRepoEntry]:
        file_list = MediaProcessor._rfind_media(path, media_filter)
        found_list = []

        for fp in file_list:
            entry = FileRepoEntry()
            entry.path = os.path.realpath(fp)
            # get the full path:
            stat = os.stat(fp)
            entry.last_mod = stat.st_mtime
            entry.size = stat.st_size
            found_list.append(entry)
        return found_list

    @staticmethod
    def _rfind_media(path, media_filter="video") -> list[str]:
        logging.getLogger("MEDIA").debug(f"_rfind_media scanning for media in {path} with filter={media_filter}")

        # Determine which formats to scan based on filter
        if media_filter == "audio":
            formats_to_scan = MediaProcessor.AUDIO_FORMATS
        elif media_filter == "video":
            formats_to_scan = MediaProcessor.VIDEO_FORMATS
        else:  # "mixed"
            formats_to_scan = MediaProcessor.supported_formats

        file_list = []
        # get all the files
        for ext in formats_to_scan:
            # this_format = directory.rglob(f"*.{ext}")
            this_format = glob.glob(f"{path}/**/*.{ext}", recursive=True)
            file_list += this_format

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
    def _process_subs(dir_path, tag, bumpdir=False, fluid=None, content_type="feature"):
        """Process all subdirectories recursively, collecting hints from all levels"""
        from collections import defaultdict

        # Get all media files recursively
        all_files = MediaProcessor._rfind_media(dir_path)

        # Group files by their immediate parent directory
        files_by_dir = defaultdict(list)
        for f in all_files:
            parent = os.path.dirname(f)
            files_by_dir[parent].append(f)

        clips = []

        # Process each directory group
        for media_dir, file_list in files_by_dir.items():
            # Collect hints from all path components
            hints = []
            rel_path = os.path.relpath(media_dir, dir_path)

            if rel_path != '.':
                path_parts = rel_path.split(os.sep)
                for part in path_parts:
                    hints += MediaProcessor._process_hints(part, tag, bumpdir)

            # Process all files in this directory with these hints
            clips += MediaProcessor._process_media(file_list, tag, hints=hints, fluid=fluid, content_type=content_type)

        return clips

    @staticmethod
    def _test_candidate_hints(hint_list, when):
        for hint in hint_list:
            if not hint.hint(when):
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

    @staticmethod
    def calc_black_segments(break_points, content_duration):
        # ensure start ordering
        break_points = sorted(break_points, key=lambda k: k["chapter_start"])
        for i in range(len(break_points)):
            if i < len(break_points) - 1:
                break_points[i]["segment_duration"] = (
                    break_points[i + 1]["chapter_start"] - break_points[i]["chapter_start"]
                )
                # Preserve or calculate chapter_end
                if "chapter_end" not in break_points[i]:
                    break_points[i]["chapter_end"] = break_points[i + 1]["chapter_start"]
            else:
                break_points[i]["segment_duration"] = content_duration - break_points[i]["chapter_start"]
                # Preserve or calculate chapter_end
                if "chapter_end" not in break_points[i]:
                    break_points[i]["chapter_end"] = content_duration

        return break_points

    @staticmethod
    def black_detect(fname, base_duration, black_min_duration=0.1, black_pixel_tresh=0.1, black_ratio_thresh=0.95):
        def min_segment(break_points):
            spx = sorted(break_points, key=lambda x: x["segment_duration"])
            return spx[0]["segment_duration"]

        def remove_min(break_points):
            spx = sorted(break_points, key=lambda x: x["segment_duration"])
            del spx[0]
            return spx

        _l = logging.getLogger("MEDIA")
        _l.info(f"Detecting black frames in {fname}")

        try:
            # Build the ffmpeg command with blackdetect filter
            filter_complex = (
                ffmpeg.input(fname)
                .filter("blackdetect", d=black_min_duration, pix_th=black_pixel_tresh, pic_th=black_ratio_thresh)
                .output("pipe:", format="null")
            )

            # Actually run the command and capture its output
            stdout, stderr = filter_complex.run(capture_stdout=True, capture_stderr=True)

            # Decode and parse - collect all black frame midpoints
            black_midpoints = []
            for line in stderr.decode("utf-8").split("\n"):
                if "blackdetect" in line:
                    try:
                        parts = line.split("]")[1].strip().split(" ")
                        info = {}
                        for part in parts:
                            if ":" in part:
                                key, value = part.split(":")
                                info[key] = float(value)
                        if info:
                            if "black_start" not in info or "black_end" not in info or "black_duration" not in info:
                                # then not a good line
                                continue

                            # Calculate middle of black frame as the break point
                            midpoint = (info["black_start"] + info["black_end"]) / 2
                            black_midpoints.append(midpoint)

                    except IndexError:
                        _l.debug(f"Skipping malformed line: {line}")
                        pass
                    except ValueError:
                        _l.info(f"Skipping invalid data in line: {line}")
                        pass
                    except Exception as e:
                        _l.info(f"An unexpected error occurred while parsing line: {line}. Error: {e}")
            _l.info(f"Found {len(black_midpoints)} black segments in {fname}")

            # Trim any near start and end times
            trimmed_midpoints = []
            for midpoint in black_midpoints:
                if midpoint > timings.MIN_1 and midpoint < base_duration - timings.MIN_1:
                    trimmed_midpoints.append(midpoint)

            # Convert midpoints to segment format: each segment goes from previous break to current break
            segments = []
            prev_point = 0
            for midpoint in trimmed_midpoints:
                segments.append({
                    "chapter_start": prev_point,
                    "chapter_end": midpoint,
                })
                prev_point = midpoint

            # Add final segment from last break to end of content
            if trimmed_midpoints:
                segments.append({
                    "chapter_start": prev_point,
                    "chapter_end": base_duration,
                })

            segmented = MediaProcessor.calc_black_segments(segments, base_duration)

            while min_segment(segmented) < timings.MIN_1 and len(segmented) > 1:
                segmented = remove_min(segmented)
                segmented = MediaProcessor.calc_black_segments(segmented, base_duration)

            return segmented

        except Exception as e:
            _l.error(f"FFmpeg hit an error detecting black frames in {fname}")
            _l.exception(e)

        return None

    @staticmethod
    def chapter_detect(fname, base_duration):
        import subprocess
        import json

        _l = logging.getLogger("MEDIA")
        _l.info(f"Detecting chapter markers in {fname}")

        try:
            # Use ffprobe with -show_chapters to extract chapter information
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", fname],
                capture_output=True,
                text=True,
            )

            probed = json.loads(result.stdout)

            chapters = []
            if "chapters" in probed and len(probed["chapters"]) > 0:
                for chapter in probed["chapters"]:
                    chapter_info = {
                        "chapter_start": float(chapter["start_time"]),
                        "chapter_end": float(chapter["end_time"]),
                    }

                    # Add title if available
                    if "tags" in chapter and "title" in chapter["tags"]:
                        chapter_info["title"] = chapter["tags"]["title"]

                    chapters.append(chapter_info)

                _l.info(f"Found {len(chapters)} chapter markers in {fname}")

                # Calculate segment durations
                for i in range(len(chapters)):
                    if i < len(chapters) - 1:
                        chapters[i]["segment_duration"] = chapters[i + 1]["chapter_start"] - chapters[i]["chapter_start"]
                    else:
                        chapters[i]["segment_duration"] = base_duration - chapters[i]["chapter_start"]

                return chapters
            else:
                _l.info(f"No chapter markers found in {fname}")
                return []

        except Exception as e:
            _l.error(f"Error detecting chapter markers in {fname}")
            _l.exception(e)

        return None
