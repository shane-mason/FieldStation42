import datetime

from fs42.catalog_entry import CatalogEntry
from pathlib import Path

from fs42.schedule_hint import DayPartHint, RangeHint


class HintAgent(object):

    @staticmethod
    def filter_candidate_entries(when:datetime.datetime, candidates:list[CatalogEntry], meta_hints):

        # let's think about what we're doing here:
        # first - separate what has a meta hint and what doesn't
        # second - from items with meta hint, get the list of ones that evaluate to true
        # finally, return the correct set:
        #   - if exclusive is true, return only those items with meta hints that are true
        #   - else, return all items without meta hints + items with meta hints that are true

        has_meta, no_meta = HintAgent.split_meta_hints(candidates, meta_hints)

        filtered_candidates = candidates
        if has_meta:
            valid_candidates = []
            exclusive_candidates = []
            for meta in has_meta:
                candidate_hints = meta["meta"]
                candidate = meta["candidate"]
                all_passed = True
                found_exclusive = False

                for candidate_hint in candidate_hints:

                    if "day_part" in candidate_hint:
                        hint = DayPartHint(candidate_hint["day_part"])
                        if not hint.hint(when):
                            all_passed = False
                            break
                    if "date_range" in candidate_hint:
                        hint = RangeHint(candidate_hint["date_range"])
                        if not hint.hint(when):
                            all_passed = False
                            break
                    if candidate_hint.get("exclusive", False):
                        found_exclusive = True


                if all_passed and not found_exclusive:
                    valid_candidates.append(candidate)
                elif found_exclusive:
                    exclusive_candidates.append(candidate)



            if len(exclusive_candidates) > 0:
                filtered_candidates = exclusive_candidates
            else:

                filtered_candidates = no_meta + valid_candidates

        return filtered_candidates


    @staticmethod
    def split_meta_hints(candidates:list[CatalogEntry], meta_hints):
        has_meta = []
        no_meta = []
        for candidate in candidates:
            if not candidate.meta_cache:
                meta = HintAgent._get_meta_hint(candidate, meta_hints)

                if meta:
                    candidate.meta_cache = {"has_meta": True, "meta" : meta}
                    has_meta.append({"meta": meta, "candidate": candidate})
                else:
                    candidate.meta_cache = {"has_meta": False}
                    no_meta.append(candidate)
            else:
                if candidate.meta_cache["has_meta"]:
                    has_meta.append({"meta": candidate.meta_cache["meta"], "candidate": candidate})
                else:
                    no_meta.append(candidate)

        return has_meta, no_meta

    @staticmethod
    def _get_meta_hint(candidate:CatalogEntry, meta_hints):
        meta = None
        for meta_hint in meta_hints:
            for tag in meta_hint["tags"]:
                if HintAgent._is_under(tag, candidate.path):
                    if not meta:
                        meta = []
                    meta.append(meta_hint)

        return meta

    @staticmethod
    def _is_under(dir_path, file_path):
        try:
            Path(file_path).relative_to(Path(dir_path))
            return True
        except ValueError:
            return False



# example:
"""
"hint_meta": [
    { "tags" : "NICKELODEON/bump/face", "day_part" : "morning"},
    { "tags" : "NICKELODEON/bump/face_winter", "day_part" : "morning", "date_range" : "December  1 - December 31"}
]
"""


# print(is_under("one/two/three", "one/two/three/file.ext"))  # True
# print(is_under("one/two/three/", "one/two/three/file.ext"))  # True
# print(is_under("one/two", "one/two/three/file.ext"))  # True
# print(is_under("/one/two", "/one/two/three/file.ext"))  # True
# print(is_under("/one/two", "one/two/three/file.ext"))  # False
# print(is_under("one/two/three/four", "one/two/three/file.ext"))  # False
# print(is_under("one/two/three/", "two/three/file.ext"))  # False
# print(is_under("one/two/three/", "one/three/file.ext"))  # False
#print(HintAgent._is_under("catalog/sitcomx/mim/protected", "catalog/sitcomx/mim/protected/Malcolm in the middle - protected.mkv"))