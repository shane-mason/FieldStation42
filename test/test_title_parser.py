import pytest
from fs42.title_parser import TitleParser

class TestTitleParser:

    def test_title_parser_no_title(self):
        episode = ""

        assert TitleParser.parse_title(episode) == ""
        

    def test_title_parser_group_title_episode(self):
        episode = "[Releasers] - Buffy the Vampire Slayer - 6"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_episode_pattern_separated(self):
        episode = "Buffy the Vampire Slayer - s6-e7 - Once More, with Feeling"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"
        
    def test_title_parser_episode_pattern_together(self):
        episode = "Buffy the Vampire Slayer - S06E07 - Once More, with Feeling"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"
    
    def test_title_parser_episode_pattern_cross(self):
        episode = "Buffy the Vampire Slayer - 06x7 - Once More, with Feeling"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_version_volume_format(self):
        episode = "Buffy the Vampire Slayer - V1-0003"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"
    
    def test_title_parser_simple_episode_numbers(self):
        episode = "Buffy the Vampire Slayer - 07 - Once More, with Feeling"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"
    
    def test_title_parser_just_title(self):
        episode = "Buffy the Vampire Slayer"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_just_title_with_nonwhitespace_separator(self):
        episode = "Buffy-the-Vampire-Slayer"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_just_title_multiple_spaces(self):
        episode = "Buffy the Vampire       Slayer"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_just_title_trailing_whitespaces(self):
        episode = "Buffy the Vampire Slayer    "

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_movie_sequel_with_space(self):
        episode = "Jaws 2"

        assert TitleParser.parse_title(episode) == "Jaws 2"

    def test_title_parser_movie_sequel_without_space(self):
        episode = "Jaws2"

        assert TitleParser.parse_title(episode) == "Jaws2"

    def test_title_parser_episode_format_with_space(self):
        episode = "Buffy the Vampire Slayer Episode 1"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_episode_format_with_title(self):
        episode = "Buffy the Vampire Slayer Episode 1 - Pilot"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_duplicate_episodes(self):
        episode = "Buffy the vampire slayer s01e03e03"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_duplicate_episodes_with_extra(self):
        episode = "Buffy the vampire slayer s01e03e03 - whatever comes after"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_year_number_combination(self):
        episode = "Top 100 1992"

        assert TitleParser.parse_title(episode) == "Top 100 1992"

    def test_title_parser_movie_sequel_with_year(self):
        episode = "Jaws 2 (1976)"

        assert TitleParser.parse_title(episode) == "Jaws 2"

    def test_title_parser_movie_with_year(self):
        episode = "Jaws (1975)"

        assert TitleParser.parse_title(episode) == "Jaws"