import random
import time

debounce_fragment = 0.1

def none_change_effect(player, reception):
    print("No change effect applied.")
    pass


def short_change_effect(player, reception):
    print("Applying short change effect.")
    prev = reception.improve_amount
    reception.improve_amount = 0

    while not reception.is_degraded():
        reception.degrade(0.2)
        player.update_filters()
        time.sleep(debounce_fragment)

    reception.improve_amount = prev


def long_change_effect(player, reception):
    print("Applying long change effect.")
    # add noise to current channel
    while not reception.is_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)

    # reception.improve(1)
    player.play_file("runtime/static.mp4")
    while not reception.is_perfect():
        reception.improve()
        player.update_filters()
        time.sleep(debounce_fragment)
    # time.sleep(1)
    while not reception.is_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)

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

class ScrambledVideoFilter(object):
    def __init__(self):
        pass
    
    def update_filter(self):
        return ""

class HLScrambledVideoFilter(ScrambledVideoFilter):
    def __init__(self):
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        
        if random.random() > .95:
            self.chaos = random.randint(40,70)
        if random.random() > .9:
            self.chaos = random.randint(10,30)
        return f"lavfi=[geq='if(mod(floor(Y/4),2),p(X,Y+{self.thrust}*sin(2*PI*X/{self.chaos})),p(X,Y))']"

class DiagonalScrambledVideoFilter(ScrambledVideoFilter):
    def __init__(self):
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        
        if random.random() > .95:
            self.chaos = random.randint(5,15)
        if random.random() > .9:
            self.chaos = random.randint(20,40)
        return f"lavfi=[geq='p(X+{self.chaos}*sin(2*PI*Y/{self.thrust}),Y)']"

class ColorInvertedScrambledVideoFilter(ScrambledVideoFilter):
    def __init__(self):
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        
        if random.random() > .95:
            self.chaos = random.randint(8,12)

        return f"lavfi=[geq='if(mod(floor(Y/{self.chaos}),2),255-p(X,Y),p(X,Y))']"

class ChunkyScrambledVideoFilter(ScrambledVideoFilter):
    def __init__(self):
        pass

    def update_filter(self):
        return "lavfi=[scale=320:240,split[base][aux];[aux]geq=r='p(X+floor((random(1000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':g='p(X+floor((random(2000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':b='p(X+floor((random(3000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)'[warped];[base][warped]overlay,scale=640:480]"