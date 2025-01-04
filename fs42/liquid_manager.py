import json

class LiquidManager(object):
    __we_are_all_one = {}
    stations = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(LiquidManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj
    
    def __init__(self):
        if not len(self.stations):
            self.load_json_stations()
