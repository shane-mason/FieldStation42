import time
from fs42.liquid_manager import LiquidManager
from fs42.station_manager import StationManager
from fs42.liquid_api import LiquidAPI
def load_all():
    return LiquidManager()

def load_station(station_name):
    config = StationManager().station_by_name(station_name)
    LiquidAPI.get_blocks(config)

start_perf = time.perf_counter()
#l = LiquidManager()
#load_all()
load_station("Games")
end_perf = time.perf_counter()
_perf = end_perf - start_perf
print(f"Loaded in in {_perf:0.4f} seconds")

