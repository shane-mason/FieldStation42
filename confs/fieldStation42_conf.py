import json

main_conf = {
    # this is the old approach using python module - this method is no longer supported and may be removed in the future
    #'stations' : [nbc_conf.station_conf, abc_conf.station_conf, pbs_conf.station_conf, cbs_conf.station_conf],

    'channel_socket' : "runtime/channel.socket"
}


def index_by_channel(channel):
    index = 0
    print("Looking for channel: ", channel)
    for station in main_conf["stations"]:
        if station["channel_number"] == channel:
            return index
        index+=1
    return None

def load_json_stations():
    import glob
    global main_conf
    cfiles = glob.glob("confs/*.json")
    stations = []
    for fname in cfiles:
        print(f"Loading configuration for: {fname}")
        with open(fname) as f:
            try:
                d = json.load(f)
                if "network_type" not in d['station_conf']:
                    print(f"Auto setting network type to standard for {d['station_conf']['network_name']}")
                    d['station_conf']["network_type"] = "standard"
                
                if "schedule_increment" not in d['station_conf']:
                    print(f"Auto setting increment buffer to 30 minutes for {d['station_conf']['network_name']}")
                    d['station_conf']["schedule_increment"] = 30
                    
                stations.append(d['station_conf'])
            except Exception as e:
                print(f"Error loading station configuration: {fname}")
                print(e)
                exit(1)

    main_conf['stations'] = sorted(stations, key=lambda station: station['channel_number'])

if 'stations' not in main_conf:
    load_json_stations()

