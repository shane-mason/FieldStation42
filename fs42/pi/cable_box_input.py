class Debounced:
    def __init__(self, initial, samples=2):
        self.value = initial
        self.samples = samples
        self.candidate = initial
        self.seen = 0

    def update(self, level):
        if level == self.value:
            self.seen = 0
            return self.value
        self.seen = self.seen + 1 if level == self.candidate else 1
        self.candidate = level
        if self.seen >= self.samples:
            self.value = level
            self.seen = 0
        return self.value


class MultiPress:
    def __init__(self, on_presses, gap=1.0, max_press=1.0):
        self.on_presses = on_presses
        self.gap = gap
        self.max_press = max_press
        self.count = 0
        self.down_at = None
        self.released_at = None
        self.held = False

    def tick(self, down, now):
        if down:
            if self.down_at is None:
                self.down_at = now
            elif not self.held and now - self.down_at >= self.max_press:
                # a hold, not a press: drop the count and ignore input until release
                self.held = True
                self.count = 0
        elif self.down_at is not None:
            if not self.held:
                self.count += 1
                self.released_at = now
            self.down_at = None
            self.held = False
        elif self.count and now - self.released_at >= self.gap:
            count = self.count
            self.count = 0
            self.on_presses(count)


class LongPress:
    def __init__(self, on_hold, hold=5.0):
        self.on_hold = on_hold
        self.hold = hold
        self.down_at = None
        self.fired = False

    def tick(self, down, now):
        if not down:
            self.down_at = None
            self.fired = False
        elif self.down_at is None:
            self.down_at = now
        elif not self.fired and now - self.down_at >= self.hold:
            self.fired = True
            self.on_hold()


class ChannelEntry:
    def __init__(self, on_step, on_digits, on_direct, timeout=1.5, max_digits=3):
        self.on_step = on_step
        self.on_digits = on_digits
        self.on_direct = on_direct
        self.timeout = timeout
        self.max_digits = max_digits
        self.digits = ""
        self.typed_at = None
        self.last_key = None

    @property
    def active(self):
        return bool(self.digits)

    def tick(self, key, now):
        if key is not None and key != self.last_key:
            self._key_down(key, now)
        self.last_key = key

        if self.digits and (len(self.digits) >= self.max_digits or now - self.typed_at > self.timeout):
            channel = int(self.digits)
            self.digits = ""
            self.on_direct(channel)

    def _key_down(self, key, now):
        if key in ("up", "down"):
            self.digits = ""
            self.on_step(key)
        else:
            self.digits += key
            self.typed_at = now
            self.on_digits(int(self.digits))
