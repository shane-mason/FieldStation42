import json

class StationManager(object):
    __we_are_all_one = {}
    stations = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        obj = super(StationManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj
    
    def __init__(self):
        if not len(self.stations):
            self.load_json_stations()

    def station_by_name(self, name):
        for station in self.stations:
            if station["network_name"] == name:
                return station
        return None
    
    def station_by_channel(self, channel):
        for station in self.stations:
            if station["channel_number"] == channel:
                return station
        return None

    def index_from_channel(self, channel):
        index = 0
        for station in self.stations:
            if station["channel_number"] == channel:
                return index
            index+=1
        return None

    def load_json_stations(self):
        import glob
        cfiles = glob.glob("confs/*.json")
        station_buffer = []
        for fname in cfiles:
            print(f"Loading configuration for: {fname}")
            with open(fname) as f:
                try:
                    d = json.load(f)
                    if "network_type" not in d['station_conf']:
                        print(f"Setting network type to standard for {d['station_conf']['network_name']}")
                        d['station_conf']["network_type"] = "standard"                
                    if "schedule_increment" not in d['station_conf']:
                        print(f"Auto setting increment buffer to 30 minutes for {d['station_conf']['network_name']}")
                        d['station_conf']["schedule_increment"] = 30
                    station_buffer.append(d['station_conf'])
                except Exception as e:
                    print(f"Error loading station configuration: {fname}")
                    print(e)
                    exit(1)

        self.stations = sorted(station_buffer, key=lambda station: station['channel_number'])

