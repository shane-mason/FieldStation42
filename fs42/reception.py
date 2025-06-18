class ReceptionStatus(object):
    __we_are_all_one = {}
    chaos = 0
    thresh = 0.01
    degrade_amount = 0.05
    improve_amount = 0.05

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(ReceptionStatus, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj

    def __init__(self):
        pass

    def is_perfect(self):
        return self.chaos == 0.0

    def is_degraded(self):
        return self.chaos > self.thresh

    def is_fully_degraded(self):
        return self.chaos == 1.0

    def degrade(self, override=0):
        if override == 0:
            self.chaos += self.degrade_amount
        else:
            self.chaos += override

        if self.chaos > 1.0:
            self.chaos = 1.0

    def improve(self, override=0):
        if override == 0:
            self.chaos -= self.improve_amount
        else:
            self.chaos -= override

        if self.chaos < self.thresh:
            self.chaos = 0.0

    def filter(self):
        if self.chaos > self.thresh:
            # between 0 and 100
            noise = self.chaos * 100
            # between 0 and .5
            v_scroll = self.chaos * 0.5
            return f"lavfi=[noise=alls={noise}:allf=t+u, scroll=h=0:v={v_scroll}]"
        else:
            return ""
