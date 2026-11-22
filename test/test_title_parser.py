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

    def test_title_parser_title1_suffix_lowercase(self):
        episode = "Buffy the Vampire Slayer - title1"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_title1_suffix_uppercase(self):
        episode = "Buffy the Vampire Slayer - TITLE1"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_title2_suffix_mixedcase(self):
        episode = "Buffy the Vampire Slayer - Title2"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_title10_suffix(self):
        episode = "Buffy the Vampire Slayer.Title10"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"

    def test_title_parser_title1_suffix_underscore_separator(self):
        episode = "Buffy_the_Vampire_Slayer_title1"

        assert TitleParser.parse_title(episode) == "Buffy The Vampire Slayer"


class TestTitleParserCustomPatterns:
    """Tests for user-defined custom patterns"""

    def test_custom_pattern_studio_prefix(self):
        """Test custom pattern that handles [Studio] prefix"""
        episode = "[Studio] My Great Show - Special Edition"
        custom_patterns = [
            (r"^\[Studio\][\s._-]+(.+?)[\s._-]+Special.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "My Great Show"

    def test_custom_pattern_hd_quality_marker(self):
        """Test custom pattern that removes HD quality markers"""
        episode = "Amazing Documentary - HD - 1080p"
        custom_patterns = [
            (r"^(.+?)[\s._-]+HD[\s._-]+\d+p.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Amazing Documentary"

    def test_custom_pattern_remaster_suffix(self):
        """Test custom pattern that removes REMASTER suffix"""
        episode = "Classic Movie_REMASTER_2023"
        custom_patterns = [
            (r"^(.+?)_REMASTER_\d{4}.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Classic Movie"

    def test_custom_pattern_priority_over_builtin(self):
        """Test that custom patterns have priority over built-in patterns"""
        episode = "[Group] Show Title - 05"

        # Without custom pattern, this would extract "Show Title"
        # With custom pattern, we want to extract the full bracketed prefix
        custom_patterns = [
            (r"^\[(.+?)\][\s._-]+.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Group"

    def test_custom_pattern_fallback_to_builtin(self):
        """Test that built-in patterns work when custom pattern doesn't match"""
        episode = "Buffy the Vampire Slayer - s01e05"

        # Custom pattern won't match, should fall back to built-in
        custom_patterns = [
            (r"^\[STUDIO\][\s._-]+(.+?)$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Buffy The Vampire Slayer"

    def test_multiple_custom_patterns(self):
        """Test multiple custom patterns in order"""
        custom_patterns = [
            (r"^\[STUDIO\][\s._-]+(.+?)[\s._-]+\d+.*$", 1),
            (r"^(.+?)[\s._-]+REMASTERED[\s._-]+.*$", 1),
            (r"^(.+?)[\s._-]+HD[\s._-]+\d+p.*$", 1)
        ]

        # Test first pattern
        episode1 = "[STUDIO] Show Name - 2023 - 01"
        assert TitleParser.parse_title(episode1, custom_patterns) == "Show Name"

        # Test second pattern
        episode2 = "Old Movie - REMASTERED - Edition"
        assert TitleParser.parse_title(episode2, custom_patterns) == "Old Movie"

        # Test third pattern
        episode3 = "Nature Documentary - HD - 720p"
        assert TitleParser.parse_title(episode3, custom_patterns) == "Nature Documentary"

    def test_custom_pattern_with_dots_as_separators(self):
        """Test custom pattern handles dot separators"""
        episode = "[Release].Great.Show.Special.2023"
        custom_patterns = [
            (r"^\[.+?\][\s._-]+(.+?)[\s._-]+Special.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Great Show"

    def test_custom_pattern_complex_capture_group(self):
        """Test custom pattern with specific capture group"""
        episode = "PREFIX - Show Title - YEAR 2023 - SUFFIX"
        custom_patterns = [
            (r"^PREFIX[\s._-]+(.+?)[\s._-]+YEAR.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Show Title"

    def test_empty_custom_patterns_list(self):
        """Test that empty custom patterns list works (uses built-in patterns)"""
        episode = "Buffy the Vampire Slayer - s01e05"
        custom_patterns = []

        assert TitleParser.parse_title(episode, custom_patterns) == "Buffy The Vampire Slayer"

    def test_none_custom_patterns(self):
        """Test that None custom patterns works (uses built-in patterns)"""
        episode = "Buffy the Vampire Slayer - s01e05"

        assert TitleParser.parse_title(episode, None) == "Buffy The Vampire Slayer"

    def test_custom_pattern_preserves_title_case_conversion(self):
        """Test that custom patterns still apply title case conversion"""
        episode = "[STUDIO] my great SHOW - special"
        custom_patterns = [
            (r"^\[STUDIO\][\s._-]+(.+?)[\s._-]+special$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "My Great Show"

    def test_custom_pattern_underscore_separator(self):
        """Test custom pattern with underscores as separators"""
        episode = "Show_Name_CUSTOM_TAG_05"
        custom_patterns = [
            (r"^(.+?)_CUSTOM_TAG_.*$", 1)
        ]

        assert TitleParser.parse_title(episode, custom_patterns) == "Show Name"