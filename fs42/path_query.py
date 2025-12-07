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

    @staticmethod
    def get_dir_from_base(full_path, base_dir):
        full = Path(full_path)
        base = Path(base_dir)
        try:
            return full.parent.relative_to(base)
        except ValueError:
            return None

    @staticmethod
    def path_starts_with(path, pattern):
        if path is None:
            return False

        path_parts = Path(path).parts
        pattern_parts = Path(pattern).parts

        if len(pattern_parts) > len(path_parts):
            return False

        return path_parts[:len(pattern_parts)] == pattern_parts

    @staticmethod
    def match_any_from_base(full_path, base_dir, patterns):
        path_from_base = PathQuery.get_dir_from_base(full_path, base_dir)

        for pattern in patterns:
            if PathQuery.path_starts_with(path_from_base, pattern):
                return pattern

        return None
