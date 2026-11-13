from fs42.pi.cec_remote import HdmiCecRemote, main, _FieldStationApi, _NumberTimer, CecKeypressMap
import pytest


class _TestCecUtilWrapper(HdmiCecRemote):
    def run_forever(self):
        pass

    def raise_power(self, on):
        self.cb_power(on)

    def raise_keypress(self, keycode):
        self.cb_button(keycode)

class _FakeApi(_FieldStationApi):
    def __init__(self):
        super().__init__()
        self.posted_channel = None
        self.specified_status = None
        self.paused = None
        self.resumed = None
        self.channel_changed = False
        self.posted_parental_pin = None

    def goto_channel(self, dest):
        self.channel_changed = True
        self.posted_channel = dest
        return type('', (object,), {"ok": True})()

    def set_status(self, status: str, channel_number: int, awaiting_pin: bool = False, pin_digits_entered: int = 0):
        self.specified_status = \
            type('', (object,), {"ok": True,
                "json": lambda a: {
                "status" : status,
                "channel_number" : channel_number,
                "awaiting_pin" : awaiting_pin,
                "pin_digits_entered" : pin_digits_entered
            }})()

    def get_status(self):
        return self.specified_status

    def pause(self):
        self.paused = True
        self.resumed = False
        return type('', (object,), {"ok": True})()

    def resume(self):
        self.resumed = True
        self.paused = False
        return type('', (object,), {"ok": True})()

    def post_parental_pin(self, number):
        self.posted_parental_pin = number
        return type('', (object,), {"ok": True})()

@pytest.fixture
def fs_api():
    return _FakeApi()

@pytest.fixture
def cec_wrapper():
    return _TestCecUtilWrapper()

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


@pytest.fixture
def timer():
    return _FakeTimer()

def test_turning_on(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):#cec_wrapper: TestCecUtilWrapper):
    main(cec_wrapper, fs_api)
    cec_wrapper.raise_power(True)
    assert fs_api.resumed == True

def test_turning_off(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):#cec_wrapper: TestCecUtilWrapper):
    main(cec_wrapper, fs_api)
    cec_wrapper.raise_power(False)
    assert fs_api.paused == True

def test_channel_up_button(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):
    main(cec_wrapper, fs_api)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_UP)
    assert fs_api.posted_channel == "up"

def test_channel_down_button(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):
    main(cec_wrapper, fs_api)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_DOWN)
    assert fs_api.posted_channel == "down"

def test_previous_channel(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):
    remote = main(cec_wrapper, fs_api)
    remote.current_channel = None
    remote.last_channel = None

    fs_api.set_status("playing", channel_number=7, awaiting_pin=True)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_UP)
    assert remote.current_channel == 7
    assert remote.last_channel is None

    # Do another test and see the update
    fs_api.set_status("playing", channel_number=15, awaiting_pin=True)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_CHANNEL_UP)
    assert remote.current_channel == 15
    assert remote.last_channel == 7

def test_previous_channel_button(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):
    remote = main(cec_wrapper, fs_api)
    remote.current_channel = 5
    remote.last_channel = 8
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_BACKWARD)
    assert fs_api.posted_channel == 8

def test_previous_channel_button_no_previous(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper):
    remote = main(cec_wrapper, fs_api)
    remote.current_channel = 5
    remote.last_channel = None
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_BACKWARD)
    # We shouldn't go anywhere if there is no previous channel
    assert fs_api.channel_changed == False

def test_number_input(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper, timer: _NumberTimer):
    main(cec_wrapper, fs_api, timer)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER3)
    assert timer.is_waiting() == True
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER5)
    assert timer.is_waiting() == True
    timer.complete_early()
    assert fs_api.channel_changed == True
    assert fs_api.posted_channel == "35"

def test_number_input_sends_immediately_at_three_chars(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper, timer: _NumberTimer):
    main(cec_wrapper, fs_api, timer)
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER3)
    assert timer.is_waiting() == True
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER5)
    assert timer.is_waiting() == True
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER7)
    assert timer.is_waiting() == False
    #timer.complete_early()
    assert fs_api.channel_changed == True
    assert fs_api.posted_channel == "357"

def test_number_input_goes_to_parental_when_waiting(fs_api: _FakeApi, cec_wrapper: _TestCecUtilWrapper, timer: _NumberTimer):
    main(cec_wrapper, fs_api, timer)
    fs_api.set_status(
        "playing",
        57,
        True,
        0
    )
    cec_wrapper.raise_keypress(CecKeypressMap.CEC_USER_CONTROL_CODE_NUMBER3)
    assert fs_api.posted_parental_pin == 3
    assert timer.is_waiting() == False




