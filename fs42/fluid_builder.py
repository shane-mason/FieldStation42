import logging
import sqlite3
import sys
import os

sys.path.append(os.getcwd())

from fs42.fluid_statements import FluidStatements
from fs42.media_processor import MediaProcessor


class FluidBuilder:
    def __init__(self):
        self.db_path = "runtime/fs42_fluid.db"
        with sqlite3.connect(self.db_path) as connection:
            FluidStatements.init_db(connection)

    def scan_file_cache(self, content_dir):
        with sqlite3.connect(self.db_path) as connection:
            # read all the files in the content dir
            logging.getLogger().info(f"Fluid file cache scan - reading {content_dir}")
            file_list = MediaProcessor.rich_find_media(content_dir)
            logging.getLogger().info(f"Comparing cache against {len(file_list)} files")
            # add any that aren't there yet
            FluidStatements.iterate_file_entries(connection, file_list)
            logging.getLogger("FLUID").info("Checking file meta for stale entries.")

    def check_file_cache(self, full_path):
        with sqlite3.connect(self.db_path) as connection:
            results = FluidStatements.check_file_cache(connection, full_path)

        return results

    def trim_file_cache(self, from_time):
        with sqlite3.connect(self.db_path) as connection:
            logging.getLogger().info("Trimming fluid file cache")
            FluidStatements.trim_file_entries(connection, from_time)

    def scan_breaks(self, dir_path):
        with sqlite3.connect(self.db_path) as connection:
            _l = logging.getLogger("break_builder")
            _l.info(f"Scanning directory {dir_path} for breaks")
            if not os.path.isdir(dir_path):
                raise FileNotFoundError(f"Directory does not exist {dir_path}")
            dir_path = os.path.realpath(dir_path)
            file_list = MediaProcessor._rfind_media(dir_path)
            for file in file_list:
                rfp = os.path.realpath(file)
                cached = self.check_file_cache(rfp)
                if cached:
                    if FluidStatements.get_break_points(connection, rfp):
                        _l.info(f"Breaks already exists for {rfp}")
                    else:
                        breaks = MediaProcessor.black_detect(rfp, cached.duration)
                        FluidStatements.add_break_points(connection, rfp, breaks)
                else:
                    _l.warning(f"{rfp} is not in fluid cache - not adding break points.")
            connection.commit()

    def get_breaks(self, fname):
        fname = os.path.realpath(fname)
        with sqlite3.connect(self.db_path) as connection:
            results = FluidStatements.get_break_points(connection, fname)
        return results


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s", level=logging.INFO)
    builder = FluidBuilder()
    # builder.scan_file_cache("catalog/nbc_content/")
    # exists = builder.check_file_cache("FieldStation42/catalog/public_domain/bextra/post-black.mov")
    builder.scan_breaks("catalog/public_domain/feature/sub/a/")
