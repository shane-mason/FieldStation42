from fs42.station_player import StationPlayer


class FakeMPV:
    def __init__(self):
        self.track_list = [
            {"type": "audio", "id": 1, "selected": True},
            {"type": "audio", "id": 2, "selected": False},
            {"type": "sub", "id": 3, "selected": False},
            {"type": "sub", "id": 4, "selected": True},
        ]
        self.audio = 1
        self.sub = 4
        self.sub_visibility = True
        self.commands = []

    def command(self, *args):
        self.commands.append(args)
        if args == ("cycle", "audio"):
            self._cycle("audio")
            return None
        if args == ("cycle", "sub"):
            self._cycle("sub")
            self.sub_visibility = self._selected("sub") is not None
            return None
        raise AssertionError(f"unexpected command: {args}")

    def _selected(self, track_type):
        for track in self.track_list:
            if track["type"] == track_type and track.get("selected"):
                return track
        return None

    def _cycle(self, track_type):
        tracks = [track for track in self.track_list if track["type"] == track_type]
        selected = self._selected(track_type)
        next_index = 0
        if selected in tracks:
            next_index = (tracks.index(selected) + 1) % len(tracks)
            selected["selected"] = False
        tracks[next_index]["selected"] = True
        if track_type == "audio":
            self.audio = tracks[next_index]["id"]
        else:
            self.sub = tracks[next_index]["id"]


def make_player():
    return StationPlayer({}, lambda: None, mpv=FakeMPV())


def test_audio_choice_is_remembered_by_track_position_for_feature_video():
    player = make_player()
    player._current_content_type = "feature"
    player._current_media_type = "video"

    assert player.mpv.audio == 1
    assert player.mpv_runtime_command("cycle_audio") is True

    assert player.mpv.audio == 2
    assert player._preferred_audio_track_index == 1


def test_subtitle_choice_is_remembered_with_visibility_for_feature_video():
    player = make_player()
    player._current_content_type = "feature"
    player._current_media_type = "video"

    assert player.mpv.sub == 4
    assert player.mpv_runtime_command("cycle_subtitles") is True

    assert player.mpv.sub == 3
    assert player._preferred_subtitle_track_index == 0
    assert player._preferred_subtitle_visibility is True


def test_choices_made_during_commercial_are_not_remembered():
    player = make_player()
    player._current_content_type = "commercial"
    player._current_media_type = "video"

    assert player.mpv_runtime_command("cycle_audio") is True

    assert player._preferred_audio_track_index is None


def test_track_preferences_only_apply_to_feature_video():
    player = make_player()
    player._preferred_audio_track_index = 1
    player._preferred_subtitle_track_index = 0
    player._preferred_subtitle_visibility = True

    player._apply_runtime_track_preferences("commercial", "video")

    assert player.mpv.audio == 1
    assert player.mpv.sub == 4

    player._apply_runtime_track_preferences("feature", "video")

    assert player.mpv.audio == 2
    assert player.mpv.sub == 3
    assert player.mpv.sub_visibility is True


def test_preferences_clear_when_programme_block_changes():
    player = make_player()
    player._set_track_preference_block("Movie A")
    player._preferred_audio_track_index = 1
    player._preferred_subtitle_track_index = 0
    player._preferred_subtitle_visibility = True

    player._set_track_preference_block("Movie A")

    assert player._preferred_audio_track_index == 1
    assert player._preferred_subtitle_track_index == 0
    assert player._preferred_subtitle_visibility is True

    player._set_track_preference_block("Movie B")

    assert player._preferred_audio_track_index is None
    assert player._preferred_subtitle_track_index is None
    assert player._preferred_subtitle_visibility is None
