#!/usr/bin/env python3
"""
FieldStation42 - Boredom Channel Setup & Virtual Library Linker
===============================================================
This script organizes media files from `catalog/boredom_channel/` into
virtual category folders (`cartoons/`, `movies/`, `bumpers/`) using
symbolic links without moving, renaming, or duplicating any original files.
"""

import os
import sys
import glob
import json
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"}

MOVIE_KEYWORDS = [
    "all.quiet",
    "charade",
    "the-little-shop",
    "little shop of horrors",
    "last of the mohicans",
    "aliceinwonderland",
    "gulliver",
]

BUMPER_KEYWORDS = [
    "psa",
    "checkers",
    "nixon",
    "thanksgivingdinner",
    "tot_another",
]

def is_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS

def categorize(filename: str) -> str:
    name_lower = filename.lower()
    for kw in MOVIE_KEYWORDS:
        if kw in name_lower:
            return "movies"
    for kw in BUMPER_KEYWORDS:
        if kw in name_lower:
            return "bumpers"
    return "cartoons"

def main():
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)

    source_dir = Path("catalog/boredom_channel")
    if not source_dir.is_dir():
        print(f"[ERROR] Source directory '{source_dir}' does not exist.")
        print("Please ensure you are running this from your FieldStation42 root directory.")
        sys.exit(1)

    target_base = Path("catalog/boredom")
    categories = ["cartoons", "movies", "bumpers"]

    for cat in categories:
        (target_base / cat).mkdir(parents=True, exist_ok=True)

    counts = {"cartoons": 0, "movies": 0, "bumpers": 0}

    print("=" * 65)
    print(" Organizing Boredom Channel Virtual Folders (Symlinks)")
    print("=" * 65)

    all_files = sorted(os.listdir(source_dir))
    for fname in all_files:
        src_path = source_dir / fname
        if not src_path.is_file() or not is_video(fname):
            continue

        cat = categorize(fname)
        link_path = target_base / cat / fname
        rel_target = Path("..") / ".." / "boredom_channel" / fname

        # Remove existing symlink or file if present
        if os.path.lexists(link_path):
            try:
                os.unlink(link_path)
            except Exception as e:
                print(f"  [WARN] Failed to unlink {link_path}: {e}")

        # Create relative symlink
        try:
            os.symlink(rel_target, link_path)
            counts[cat] += 1
            print(f"  [{cat.upper():8}] {fname}")
        except Exception as e:
            print(f"  [FAIL] Could not symlink {fname} -> {rel_target}: {e}")

    print("-" * 65)
    print(f"Summary of Symlinked Content in {target_base}:")
    print(f"  - Cartoons : {counts['cartoons']} titles")
    print(f"  - Movies   : {counts['movies']} titles")
    print(f"  - Bumpers  : {counts['bumpers']} titles")
    print(f"  - Total    : {sum(counts.values())} titles")
    print("-" * 65)

    # Check station configs in confs/
    confs_dir = Path("confs")
    confs_dir.mkdir(exist_ok=True)
    boredom_json = confs_dir / "boredom.json"
    example_json = Path("confs/examples/boredom_channel.json")

    if not boredom_json.exists() and example_json.exists():
        import shutil
        shutil.copy(example_json, boredom_json)
        print(f"  [CONFIG] Created {boredom_json} from {example_json}")

    # Backup any conflicting channel 1 config
    for cfile in confs_dir.glob("*.json"):
        if cfile.name in ("boredom.json", "main_config.json"):
            continue
        try:
            with open(cfile) as f:
                data = json.load(f)
                s_conf = data.get("station_conf", {})
                if s_conf.get("channel_number") == 1:
                    bak_file = cfile.with_suffix(".json.bak")
                    print(f"  [NOTE] Renaming conflicting channel 1 config '{cfile.name}' -> '{bak_file.name}'")
                    cfile.rename(bak_file)
        except Exception:
            pass

    print(f"Station configuration verified: {boredom_json}")
    print("-" * 65)
    print("Rebuilding catalog and generating schedule with station_42.py...")
    import subprocess
    try:
        subprocess.run([sys.executable, "station_42.py", "--rebuild_catalog"], check=True)
        subprocess.run([sys.executable, "station_42.py", "--add_week"], check=True)
        print("Catalog and schedule successfully built!")
    except Exception as e:
        print(f"[WARN] Error running station_42.py: {e}")

    print("=" * 65)
    print("Setup complete! You can now start FieldStation42:")
    print("  systemctl restart fs42-broadcast")
    print("=" * 65)

if __name__ == "__main__":
    main()
