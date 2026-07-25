from fs42.metadata_io import MetadataIO


class TestNormalize:

    def test_legacy_audio_row_gets_year_and_type(self):
        # Rows written before normalization used `date` and had no `type`.
        legacy = {"title": "Long Way Down", "artist": "Robert DeLong",
                  "album": "Long Way Down", "date": "2014", "genre": "Alternative Rock"}
        assert MetadataIO.normalize(legacy) == {
            "title": "Long Way Down", "artist": "Robert DeLong",
            "album": "Long Way Down", "year": "2014", "genre": "Alternative Rock",
            "type": "music",
        }

    def test_already_normalized_is_unchanged(self):
        meta = {"type": "movie", "title": "The Thing", "year": "1982"}
        assert MetadataIO.normalize(meta) == meta

    def test_year_wins_when_both_present(self):
        meta = MetadataIO.normalize({"title": "X", "date": "2014", "year": "2015"})
        assert meta["year"] == "2015"

    def test_does_not_mutate_input(self):
        original = {"title": "X", "date": "2014"}
        MetadataIO.normalize(original)
        assert original == {"title": "X", "date": "2014"}

    def test_non_dict_passthrough(self):
        assert MetadataIO.normalize(None) is None
