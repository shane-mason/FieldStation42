import pytest
import urllib.parse
from fs42.autobump_agent import AutoBumpAgent
from fs42.catalog_entry import CatalogEntry
from fs42.station_manager import StationManager


class TestAutoBumpAgent:

    def test_generate_bump_query_basic(self):
        """Test basic query generation with required title only."""
        config = {'title': 'FSTV'}
        result = AutoBumpAgent.generate_bump_query(config)
        assert result == 'title=FSTV'

    def test_generate_bump_query_with_subtitle(self):
        """Test query generation with title and subtitle."""
        config = {
            'title': 'FSTV',
            'subtitle': 'Field Station Television'
        }
        result = AutoBumpAgent.generate_bump_query(config)
        # Parse the result to check parameters
        parsed = urllib.parse.parse_qs(result)
        assert parsed['title'] == ['FSTV']
        assert parsed['subtitle'] == ['Field Station Television']

    def test_generate_bump_query_complete_config(self):
        """Test query generation with all parameters."""
        config = {
            'title': 'TESTTV',
            'subtitle': 'Test Broadcasting Network',
            'variation': 'modern',
            'detail1': 'Channel 42',
            'detail2': 'testtv.com',
            'detail3': '24/7 Testing',
            'bg_color': '#ff0000',
            'fg_color': '#ffffff',
            'next_network': 'testtv',
            'duration': 15000
        }
        result = AutoBumpAgent.generate_bump_query(config)
        parsed = urllib.parse.parse_qs(result)
        
        assert parsed['title'] == ['TESTTV']
        assert parsed['subtitle'] == ['Test Broadcasting Network']
        assert parsed['variation'] == ['modern']
        assert parsed['detail1'] == ['Channel 42']
        assert parsed['detail2'] == ['testtv.com']
        assert parsed['detail3'] == ['24/7 Testing']
        assert parsed['bg_color'] == ['#ff0000']
        assert parsed['fg_color'] == ['#ffffff']
        assert parsed['next_network'] == ['testtv']
        assert parsed['duration'] == ['15000000']

    def test_generate_bump_query_missing_title(self):
        """Test that missing title raises ValueError."""
        config = {'subtitle': 'Field Station Television'}
        with pytest.raises(ValueError, match="title is required"):
            AutoBumpAgent.generate_bump_query(config)

    def test_generate_bump_query_none_values_excluded(self):
        """Test that None values are excluded from query string."""
        config = {
            'title': 'FSTV',
            'subtitle': None,
            'variation': 'retro'
        }
        result = AutoBumpAgent.generate_bump_query(config)
        parsed = urllib.parse.parse_qs(result)
        
        assert parsed['title'] == ['FSTV']
        assert parsed['variation'] == ['retro']
        assert 'subtitle' not in parsed

    def test_generate_bump_query_url_encoding(self):
        """Test that special characters are properly URL encoded."""
        config = {
            'title': 'LOCAL NEWS',
            'subtitle': 'News & Weather',
            'detail1': '50% chance of rain'
        }
        result = AutoBumpAgent.generate_bump_query(config)
        # Should contain URL-encoded ampersand and percent
        assert 'News+%26+Weather' in result or 'News%20%26%20Weather' in result
        assert '50%25+chance' in result or '50%25%20chance' in result

    def test_message_bump(self):
        """Test message_bump creates proper BlockPlanEntry."""
        config = {
            'title': 'FSTV',
            'subtitle': 'Field Station Television',
            'duration': 10
        }
        base_url = "http://test.com/bump.html"
        
        result = AutoBumpAgent.message_bump(config, base_url)
        
        assert isinstance(result, CatalogEntry)
        assert result.duration == 10
        assert result.path.startswith(':autobump:=')
        assert base_url in result.path
        assert 'title=FSTV' in result.path

    def test_next_up_bump(self):
        """Test next_up_bump creates proper BlockPlanEntry with network info."""
        config = {
            'title': 'TESTTV',
            'duration': 15
        }
        base_url = "http://test.com/bump.html"
        network_name = "TESTTV Network"
        
        result = AutoBumpAgent.next_up_bump(config, base_url, network_name)
        
        assert isinstance(result, CatalogEntry)
        assert result.duration == 15
        assert result.path.startswith(':autobump:=')
        assert base_url in result.path
        assert 'title=TESTTV' in result.path
        assert 'subtitle=Coming+up+on+TESTTV+Network' in result.path or 'subtitle=Coming%20up%20on%20TESTTV%20Network' in result.path
        assert 'next_network=TESTTV+Network' in result.path or 'next_network=TESTTV%20Network' in result.path

    def test_gen_bumps_no_autobump_config(self):
        """Test gen_bumps returns None blocks when autobump not configured."""
        station_config = {
            "network_name": "FSTV"
        }
        result = AutoBumpAgent.gen_bumps(station_config)
        
        assert result["start_block"] is None
        assert result["end_block"] is None

    def test_gen_bumps_with_config(self):
        """Test gen_bumps creates both start and end blocks."""
        station_config = {
            "autobump": {
                "title": "FSTV",
                "subtitle": "Field Station Television",
                "variation": "corporate"
            },
            "network_name": "FSTV"
        }
        result = AutoBumpAgent.gen_bumps(station_config)

        assert result["message_bump"] is not None
        assert result["next_bump"] is not None
        assert isinstance(result["message_bump"], CatalogEntry)
        assert isinstance(result["next_bump"], CatalogEntry)
        assert result["message_bump"].duration == 7  # default duration
        assert result["next_bump"].duration == 7

    def test_gen_bumps_with_custom_duration(self):
        """Test gen_bumps uses custom duration when provided."""
        station_config = {
            "autobump": {
                "title": "TESTTV",
                "duration": 20
            },
            "network_name": "TESTTV"
        }
        result = AutoBumpAgent.gen_bumps(station_config)

        assert result["message_bump"].duration == 20
        assert result["next_bump"].duration == 20

    def test_gen_bumps_modifies_end_bump_config(self):
        """Test that gen_bumps properly modifies config for end bump."""
        original_config = {
            "title": "FSTV",
            "subtitle": "Original Subtitle"
        }
        station_config = {
            "autobump": original_config.copy(),
            "network_name": "FSTV Networks"
        }
        
        result = AutoBumpAgent.gen_bumps(station_config)

        # next_bump should have modified subtitle and next_network
        end_path = result["next_bump"].path
        assert 'subtitle=Coming+up+on+FSTV+Networks' in end_path or 'subtitle=Coming%20up%20on%20FSTV%20Networks' in end_path
        assert 'next_network=FSTV+Networks' in end_path or 'next_network=FSTV%20Networks' in end_path

    def test_is_autobump_url_with_prefix(self):
        """Test is_autobump_url returns True for URLs with autobump prefix."""
        url_with_prefix = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=FSTV"
        assert AutoBumpAgent.is_autobump_url(url_with_prefix) is True

    def test_is_autobump_url_without_prefix(self):
        """Test is_autobump_url returns False for URLs without autobump prefix."""
        url_without_prefix = "http://127.0.0.1:4242/static/bump/bump.html?title=FSTV"
        assert AutoBumpAgent.is_autobump_url(url_without_prefix) is False

    def test_is_autobump_url_empty_string(self):
        """Test is_autobump_url returns False for empty string."""
        assert AutoBumpAgent.is_autobump_url("") is False

    def test_extract_url_with_prefix(self):
        """Test extract_url removes the autobump prefix correctly."""
        prefixed_url = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=Public%20Domain%20TV&subtitle=Coming%20up%20on%20PublicDomain&variation=retro&detail1=If%20you%20like%20the%20old%20stuff&detail2=that%20has%20bad%20messaging&detail3=24%2F7%20Testing&next=PublicDomain&duration=10"
        expected_url = "http://127.0.0.1:4242/static/bump/bump.html?title=Public%20Domain%20TV&subtitle=Coming%20up%20on%20PublicDomain&variation=retro&detail1=If%20you%20like%20the%20old%20stuff&detail2=that%20has%20bad%20messaging&detail3=24%2F7%20Testing&next=PublicDomain&duration=10"
        
        result = AutoBumpAgent.extract_url(prefixed_url)
        assert result == expected_url

    def test_extract_url_without_prefix(self):
        """Test extract_url returns original URL when no prefix present."""
        url_without_prefix = "http://127.0.0.1:4242/static/bump/bump.html?title=FSTV"
        result = AutoBumpAgent.extract_url(url_without_prefix)
        assert result == url_without_prefix

    def test_extract_url_example_matching_url(self):
        """Test extract_url with the specific example URL provided."""
        example_url = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=Public%20Domain%20TV&subtitle=Coming%20up%20on%20PublicDomain&variation=retro&detail1=If%20you%20like%20the%20old%20stuff&detail2=that%20has%20bad%20messaging&detail3=24%2F7%20Testing&next=PublicDomain&duration=10"
        expected = "http://127.0.0.1:4242/static/bump/bump.html?title=Public%20Domain%20TV&subtitle=Coming%20up%20on%20PublicDomain&variation=retro&detail1=If%20you%20like%20the%20old%20stuff&detail2=that%20has%20bad%20messaging&detail3=24%2F7%20Testing&next=PublicDomain&duration=10"

        result = AutoBumpAgent.extract_url(example_url)
        assert result == expected

    def test_generate_bump_query_with_bg_music_filename(self, monkeypatch):
        """Test that bg_music filename gets converted to full URL."""
        monkeypatch.setitem(StationManager().server_conf, "server_port", 4242)
        config = {
            'title': 'TESTTV',
            'bg_music': 'retro.mp3'
        }
        result = AutoBumpAgent.generate_bump_query(config)
        parsed = urllib.parse.parse_qs(result)

        assert parsed['title'] == ['TESTTV']
        assert parsed['bg_music'] == ['http://127.0.0.1:4242/static/bump/music/retro.mp3']

    def test_generate_bump_query_with_bg_music_url(self):
        """Test that full bg_music URL is preserved."""
        config = {
            'title': 'TESTTV',
            'bg_music': 'https://example.com/music/corporate.mp3'
        }
        result = AutoBumpAgent.generate_bump_query(config)
        parsed = urllib.parse.parse_qs(result)

        assert parsed['title'] == ['TESTTV']
        assert parsed['bg_music'] == ['https://example.com/music/corporate.mp3']

class TestAutoBumpConfigIsolation:

    def _station(self):
        return {"network_name": "Toons", "autobump": {"title": "Toons TV", "subtitle": "All cartoons, all day"}}

    def test_gen_bumps_leaves_station_config_untouched(self):
        station = self._station()
        AutoBumpAgent.gen_bumps(station)
        assert station["autobump"] == {"title": "Toons TV", "subtitle": "All cartoons, all day"}

    def test_subtitle_survives_later_breaks(self):
        station = self._station()
        AutoBumpAgent.gen_bumps(station)
        second = AutoBumpAgent.gen_bumps(station)
        assert "subtitle=All%20cartoons%2C%20all%20day" in second["message_bump"].path

    def test_fill_does_not_change_later_bump_length(self):
        station = self._station()
        AutoBumpAgent.fill_block(station, 3600)
        assert AutoBumpAgent.gen_bumps(station)["message_bump"].duration == 7

    def test_off_air_fill_leaves_off_air_config_untouched(self):
        station = {"network_name": "Toons", "off_air_autobump": {"title": "Toons TV"}}
        fill = AutoBumpAgent.fill_block(station, 3600)
        assert fill.duration == 3600
        assert station["off_air_autobump"] == {"title": "Toons TV"}

    def test_bg_video_probed_once(self, monkeypatch):
        calls = []
        monkeypatch.setattr(AutoBumpAgent, "_bg_video_durations", {})
        monkeypatch.setattr(AutoBumpAgent, "_probe_bg_video_duration", staticmethod(lambda v: calls.append(v) or 12.0))
        station = {"network_name": "Toons", "autobump": {"title": "Toons TV", "bg_video": "intro.webm"}}
        for _ in range(3):
            assert AutoBumpAgent.gen_bumps(station)["message_bump"].duration == 12.0
        assert calls == ["intro.webm"]


class TestLocalServerPort:

    @pytest.fixture(autouse=True)
    def port_4300(self, monkeypatch):
        monkeypatch.setitem(StationManager().server_conf, "server_port", 4300)

    def test_local_server_url_uses_server_port(self):
        assert StationManager().local_server_url() == "http://127.0.0.1:4300"

    def test_generated_autobumps_use_server_port(self):
        bumps = AutoBumpAgent.gen_bumps({"network_name": "T", "autobump": {"title": "T"}})
        for bump in bumps.values():
            assert AutoBumpAgent.extract_url(bump.path).startswith("http://127.0.0.1:4300/static/bump/bump.html?")

    def test_off_air_fill_uses_server_port(self):
        fill = AutoBumpAgent.fill_block({"network_name": "T", "off_air_autobump": {"title": "T"}}, 3600)
        assert AutoBumpAgent.extract_url(fill.path).startswith("http://127.0.0.1:4300/")

    def test_music_and_video_files_use_server_port(self):
        parsed = urllib.parse.parse_qs(AutoBumpAgent.generate_bump_query({"title": "T", "bg_music": "logo1.mp3", "bg_video": "intro.webm"}))
        assert parsed["bg_music"] == ["http://127.0.0.1:4300/static/bump/music/logo1.mp3"]
        assert parsed["bg_video"] == ["http://127.0.0.1:4300/static/bump/video/intro.webm"]
