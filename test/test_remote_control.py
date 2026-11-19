import pytest

from fs42.pi.remote_controller import BaseRemote, main, _FieldStationApi, _NumberTimer, ButtonNames


class _TestBaseRemoteWrapper(BaseRemote):
    def run_forever(self):
        pass

    def raise_button(self, button):
        self.button_callback(button)


class _FakeApi(_FieldStationApi):
    def __init__(self):
        super().__init__()
        self.posted_channel = None
        self.specified_status = None
        self.posted_volume = None
        self.paused = None
        self.resumed = None
        self.channel_changed = False
        self.posted_parental_pin = None

    def goto_channel(self, dest):
        self.channel_changed = True
        self.posted_channel = dest
        return True

    def set_status(self, status: str, channel_number: int, awaiting_pin: bool = False, pin_digits_entered: int = 0):
        self.specified_status = {
            "status": status,
            "channel_number": channel_number,
            "awaiting_pin": awaiting_pin,
            "pin_digits_entered": pin_digits_entered
        }

    def get_status(self):
        return self.specified_status

    def power(self, start_or_stop):
        if start_or_stop == "start":
            self.resumed = True
            self.paused = False
        elif start_or_stop == "stop":
            self.resumed = False
            self.paused = True
        return True

    def volume(self, change):
        self.posted_volume = change
        return True

    def post_parental_pin(self, number):
        self.posted_parental_pin = number
        return True

    def show_guide(self):
        return True

    def mpv_command_pressed(self, action):
        return True


@pytest.fixture
def fs_api():
    return _FakeApi()


@pytest.fixture
def remote_input():
    return _TestBaseRemoteWrapper()


class _FakeTimer(_NumberTimer):
    def __init__(self):
        super().__init__()
        self.waiting = False

    def start(self, duration):
        self.waiting = True
        pass

    # Use this for testing to also signal the timer running out
    def complete_early(self):
        self.waiting = False
        self.on_complete()

    def is_waiting(self):
        return self.waiting

    def wait_for_status(self):
        pass


@pytest.fixture
def timer():
    return _FakeTimer()


def test_turning_on(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):  # cec_wrapper: TestCecUtilWrapper):
    main(remote_input, fs_api)
    remote_input.raise_button(ButtonNames.POWER_UP)
    assert fs_api.resumed == True


def test_turning_off(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):  # cec_wrapper: TestCecUtilWrapper):
    main(remote_input, fs_api)
    remote_input.raise_button(ButtonNames.POWER_DOWN)
    assert fs_api.paused == True


def test_volume_down_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    main(remote_input, fs_api)
    remote_input.raise_button(ButtonNames.VOLUME_DOWN)
    assert fs_api.posted_volume == "down"


def test_volume_up_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    main(remote_input, fs_api)
    remote_input.raise_button(ButtonNames.VOLUME_UP)
    assert fs_api.posted_volume == "up"


def test_mute_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    main(remote_input, fs_api)
    remote_input.raise_button(ButtonNames.MUTE)
    assert fs_api.posted_volume == "mute"


def test_channel_up_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    main(remote_input, fs_api)
    fs_api.set_status(
        "playing",
        57,
        False,
        0
    )
    remote_input.raise_button(ButtonNames.CHANNEL_UP)
    assert fs_api.posted_channel == "up"


def test_channel_down_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    main(remote_input, fs_api)
    fs_api.set_status(
        "playing",
        57,
        False,
        0
    )
    remote_input.raise_button(ButtonNames.CHANNEL_DOWN)
    assert fs_api.posted_channel == "down"


def test_previous_channel(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    remote = main(remote_input, fs_api)
    remote.current_channel = None
    remote.last_channel = None

    fs_api.set_status("playing", channel_number=7, awaiting_pin=False)
    remote_input.raise_button(ButtonNames.CHANNEL_UP)
    assert remote.current_channel == 7
    assert remote.last_channel is None

    # Do another test and see the update
    fs_api.set_status("playing", channel_number=15, awaiting_pin=False)
    remote_input.raise_button(ButtonNames.CHANNEL_UP)
    assert remote.current_channel == 15
    assert remote.last_channel == 7


def test_previous_channel_button(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    remote = main(remote_input, fs_api)
    remote.current_channel = 5
    remote.last_channel = 8
    fs_api.set_status(
        "playing",
        8,
        False,
        0
    )
    remote_input.raise_button(ButtonNames.BACK)
    assert fs_api.posted_channel == 8


def test_previous_channel_button_no_previous(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper):
    remote = main(remote_input, fs_api)
    remote.current_channel = 5
    remote.last_channel = None
    remote_input.raise_button(ButtonNames.BACK)
    # We shouldn't go anywhere if there is no previous channel
    assert fs_api.channel_changed == False


def test_number_input(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper, timer: _NumberTimer):
    main(remote_input, fs_api, timer)
    fs_api.set_status(
        "playing",
        57,
        False,
        0
    )
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "3")
    assert timer.is_waiting() == True
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "5")
    assert timer.is_waiting() == True
    timer.complete_early()
    assert fs_api.channel_changed == True
    assert fs_api.posted_channel == "35"


def test_number_input_sends_immediately_at_three_chars(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper,
                                                       timer: _NumberTimer):
    main(remote_input, fs_api, timer)
    fs_api.set_status(
        "playing",
        57,
        False,
        0
    )
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "3")
    assert timer.is_waiting() == True
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "5")
    assert timer.is_waiting() == True
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "7")
    assert timer.is_waiting() == False

    assert fs_api.channel_changed == True
    assert fs_api.posted_channel == "357"


def test_number_input_goes_to_parental_when_waiting(fs_api: _FakeApi, remote_input: _TestBaseRemoteWrapper,
                                                    timer: _NumberTimer):
    main(remote_input, fs_api, timer)
    fs_api.set_status(
        "playing",
        57,
        True,
        0
    )
    remote_input.raise_button(ButtonNames.NUMBER_PREFIX + "3")
    assert fs_api.posted_parental_pin == '3'
    assert timer.is_waiting() == False
