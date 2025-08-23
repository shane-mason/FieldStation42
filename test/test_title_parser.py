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