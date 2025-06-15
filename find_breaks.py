# Tries to finds appropriate commercial break points in videos using either existing chapter marks or ffmpeg's blackdetect filter.

import os, sys, re, json
import ffmpeg
import argparse
import tempfile

from fs42.media_processor import MediaProcessor

def strat_chapters(filepath, args):
    break_points = []
    probe_out = ffmpeg.probe(filepath, show_chapters=None)
    for chapter in probe_out["chapters"]:
        break_points.append(float(chapter["start_time"]))
    return break_points

def strat_blackdetect(filepath, duration, args, min_duration=0.5, black_level=0.1, black_amount=0.999):
    _, err = (
        ffmpeg
        .input(filepath, ss=args.ignore_start, to=(duration - args.ignore_end))
        .filter('blackdetect', d=min_duration, pix_th=black_level, pic_th=black_amount)
        .output('-', format='null')
        .global_args('-copyts', '-hide_banner', '-nostats')
        .run(capture_stdout=False, capture_stderr=True)
    )

    # Example blackdetect line:
    # [blackdetect @ 0x5567b5806dc0] black_start:300.467 black_end:302.844 black_duration:2.377
    break_points = re.findall(r'\n\[blackdetect.+black_start:([^ ]+) black_end:([^ ]+)',err.decode('utf-8'))

    # Reduce from (start, end) tuple to just the mid point
    break_points = [(float(x[0]) + float(x[1]))*0.5 for x in break_points]

    return break_points

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument('files', type=str, nargs='*')
    parser.add_argument('--db', dest='dbpath', action='store', type=str, required=True, help='The json file the results will be stored in.')
    parser.add_argument('--ignore_start', dest='ignore_start', action='store', type=float, default=120.0, help='Ignore any break found before this time (in seconds).')
    parser.add_argument('--ignore_end', dest='ignore_end', action='store', type=float, default=180.0, help='Ignore any break found after this time from the end (in seconds).')
    parser.add_argument('--min_segment_time', dest='min_segment_time', action='store', type=float, default=120.0, help='Minimum time between breaks (in seconds).')
    parser.add_argument('--strategy', dest='strategy', choices=['auto', 'chapter', 'blackdetect'], default='auto', help='Strategy used to detect break points. Note: blackdetect needs to scan each frame of the video and can be quite slow.')
    parser.add_argument('-f', '--force', dest='force', action='store_true', help='Repeat operation even if already in the database.')

    args = parser.parse_args()

    if os.path.exists(args.dbpath):
        with open(args.dbpath, "r") as f:
            db = json.load(f)
    else:
        db = {}

    for filepath in args.files:
        if not args.force and filepath in db:
            print(f"Skipping {filepath}")
            continue

        duration = MediaProcessor._get_duration(filepath)
        if duration <= 0:
            print(f"Failed to determine duration '{filepath}'")
            continue

        if args.strategy == 'chapter' or args.strategy == 'auto':
            break_points = strat_chapters(filepath, args)
        if args.strategy == 'blackdetect' or (args.strategy == 'auto' and len(break_points) == 0):
            break_points = strat_blackdetect(filepath, duration, args)

        if not break_points or len(break_points) == 0:
            print(f"No break points found for '{filepath}'")
            continue

        # Filter entries in the ignore periods
        break_points = [x for x in break_points if x >= args.ignore_start and x < (duration - args.ignore_end)]

        # Filter entries that don't meet the minimum segment time
        if len(break_points) > 0:
            prior = break_points[0]
            filtered = [prior]
            for bp in break_points[1:]:
                if bp - prior < args.min_segment_time:
                    continue
                filtered.append(bp)
                prior = bp
            break_points = filtered

        if len(break_points) == 0:
            print(f"No valid break points found for '{filepath}'")
            continue

        # Add end of video break
        break_points.append(duration)

        db[filepath] = break_points
        print(f'"{filepath}": {str(break_points)}')

    tempf, tempfname = tempfile.mkstemp()
    json.dump(db, os.fdopen(tempf, "w"))
    os.replace(tempfname, args.dbpath)

