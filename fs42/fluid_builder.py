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
            connection.commit()

    def check_file_cache(self, full_path):
        with sqlite3.connect(self.db_path) as connection:
            results = FluidStatements.check_file_cache(connection, full_path)
            connection.commit()

        return results

    def trim_file_cache(self, from_time):
        with sqlite3.connect(self.db_path) as connection:
            logging.getLogger().info("Trimming fluid file cache")
            FluidStatements.trim_file_entries(connection, from_time)
            connection.commit()


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s", level=logging.INFO)
    builder = FluidBuilder()
    builder.scan_file_cache("catalog/nbc_content/")
    exists = builder.check_file_cache("/home/wrongdog/FieldStation42/catalog/public_domain/bextra/post-black.mov")
