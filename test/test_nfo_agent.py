import pytest
from fs42.nfo_agent import NFOAgent


class TestParseNfoString:

    def test_musicvideo(self):
        content = """<?xml version='1.0' encoding='utf-8'?>
        <musicvideo>
          <title>No Rain</title>
          <artist>Blind Melon</artist>
          <album>Live at the Palace</album>
          <year>1993</year>
          <genre>Alternative Rock</genre>
        </musicvideo>"""
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {
            "type": "music",
            "title": "No Rain",
            "artist": "Blind Melon",
            "album": "Live at the Palace",
            "year": "1993",
            "genre": "Alternative Rock",
        }

    def test_musicvideo_year_falls_back_to_premiered(self):
        content = """<musicvideo>
          <title>Song</title>
          <artist>Someone</artist>
          <premiered>1988-05-01</premiered>
        </musicvideo>"""
        meta = NFOAgent.parse_nfo_string(content)
        assert meta["year"] == "1988"

    def test_movie(self):
        content = """<movie>
          <title>The Thing</title>
          <year>1982</year>
          <plot>A shape-shifting alien.</plot>
          <genre>Horror</genre>
        </movie>"""
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {
            "type": "movie",
            "title": "The Thing",
            "year": "1982",
            "plot": "A shape-shifting alien.",
            "genre": "Horror",
        }

    def test_movie_plot_falls_back_to_outline(self):
        content = "<movie><title>X</title><outline>short</outline></movie>"
        meta = NFOAgent.parse_nfo_string(content)
        assert meta["plot"] == "short"

    def test_episodedetails_converts_season_episode_to_int(self):
        content = """<episodedetails>
          <title>The Constant</title>
          <showtitle>Lost</showtitle>
          <season>4</season>
          <episode>5</episode>
          <aired>2008-02-28</aired>
          <plot>Desmond.</plot>
        </episodedetails>"""
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {
            "type": "episode",
            "title": "The Constant",
            "show_title": "Lost",
            "season": 4,
            "episode": 5,
            "aired": "2008-02-28",
            "plot": "Desmond.",
        }

    def test_tvshow(self):
        content = "<tvshow><title>Lost</title><year>2004</year></tvshow>"
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {"type": "tvshow", "title": "Lost", "year": "2004"}

    def test_unknown_tag_generic_fallback(self):
        content = "<artist><title>Blind Melon</title><genre>Rock</genre></artist>"
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {"type": "artist", "title": "Blind Melon", "genre": "Rock"}

    def test_unknown_tag_without_title_is_none(self):
        content = "<artist><formed>1990</formed></artist>"
        assert NFOAgent.parse_nfo_string(content) is None

    def test_empty_fields_are_dropped(self):
        content = "<movie><title>X</title><year></year><plot></plot></movie>"
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {"type": "movie", "title": "X"}

    def test_plain_text_fallback(self):
        content = "Blind Melon\nNo Rain\nLive at the Palace\n1993\n"
        meta = NFOAgent.parse_nfo_string(content)
        assert meta == {
            "type": "plaintext",
            "title": "Blind Melon",
            "lines": ["Blind Melon", "No Rain", "Live at the Palace", "1993"],
        }

    def test_plain_text_caps_at_max_lines(self):
        content = "\n".join(str(i) for i in range(10))
        meta = NFOAgent.parse_nfo_string(content)
        assert len(meta["lines"]) == 5

    def test_empty_content_is_none(self):
        assert NFOAgent.parse_nfo_string("   \n  \n") is None


class TestOverlayLines:

    def test_music_order_is_artist_title_album_year(self):
        meta = {
            "type": "music",
            "title": "No Rain",
            "artist": "Blind Melon",
            "album": "Live at the Palace",
            "year": "1993",
        }
        assert NFOAgent.overlay_lines(meta) == [
            "Blind Melon", "No Rain", "Live at the Palace", "1993",
        ]

    def test_music_skips_missing_fields(self):
        meta = {"type": "music", "title": "Solo", "artist": "Nobody"}
        assert NFOAgent.overlay_lines(meta) == ["Nobody", "Solo"]

    def test_plaintext_returns_lines(self):
        meta = {"type": "plaintext", "lines": ["a", "b", "c"]}
        assert NFOAgent.overlay_lines(meta) == ["a", "b", "c"]

    def test_movie_is_not_overlay_eligible(self):
        meta = {"type": "movie", "title": "The Thing", "year": "1982"}
        assert NFOAgent.overlay_lines(meta) is None

    def test_episode_is_not_overlay_eligible(self):
        meta = {"type": "episode", "title": "The Constant"}
        assert NFOAgent.overlay_lines(meta) is None

    def test_none_is_none(self):
        assert NFOAgent.overlay_lines(None) is None


class TestDisplayFields:

    def test_music(self):
        meta = {"type": "music", "title": "No Rain", "artist": "Blind Melon", "album": "LATP"}
        assert NFOAgent.display_fields(meta) == {
            "title": "No Rain", "info": "Blind Melon", "description": "LATP",
        }

    def test_movie(self):
        meta = {"type": "movie", "title": "The Thing", "year": "1982", "plot": "Alien."}
        assert NFOAgent.display_fields(meta) == {
            "title": "The Thing", "info": "1982", "description": "Alien.",
        }

    def test_episode(self):
        meta = {"type": "episode", "title": "The Constant", "show_title": "Lost", "plot": "D."}
        assert NFOAgent.display_fields(meta) == {
            "title": "The Constant", "info": "Lost", "description": "D.",
        }

    def test_plaintext(self):
        meta = {"type": "plaintext", "lines": ["a", "b", "c", "d"]}
        assert NFOAgent.display_fields(meta) == {
            "title": "a", "info": "b", "description": "c",
        }

    def test_none_is_none(self):
        assert NFOAgent.display_fields(None) is None
