from pathlib import Path


class PathQuery:
    """Utility class for path comparison and querying operations."""

    @staticmethod
    def path_ends_with_relative(full_path, relative_path):

        full = Path(full_path)
        rel = Path(relative_path)

        # Get only the directory parts (exclude filename)
        full_dir_parts = full.parent.parts
        rel_parts = rel.parts

        # Check if we have enough parts to match
        if len(rel_parts) > len(full_dir_parts):
            return False

        # Compare the ending directory parts
        return full_dir_parts[-len(rel_parts):] == rel_parts

    @staticmethod
    def path_matches_any_relative(full_path, relative_paths):

        for relative_path in relative_paths:
            if PathQuery.path_ends_with_relative(full_path, relative_path):
                return relative_path
        return None
