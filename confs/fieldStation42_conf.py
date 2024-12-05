import json
import os

main_conf = {
    # this is the old approach using python module - this method is no longer supported and may be removed in the future
    #'stations' : [nbc_conf.station_conf, abc_conf.station_conf, pbs_conf.station_conf, cbs_conf.station_conf],

    'channel_socket' : "runtime/channel.socket",
    'guide_socket': "/tmp/fs42guide.socket"
}

def load_json_stations():
    import glob
    global main_conf
    cfiles = glob.glob("confs/*.json")
    stations = []
    for fname in cfiles:
        print(os.path.basename(fname))
        with open(fname) as f:
            try:
                d = json.load(f)
                #if os.path.basename(fname) == "guide.json":
                #    main_conf['guide'] = d['guide_conf']
                #else:
                stations.append(d['station_conf'])
            except Exception as e:
                print(f"Error loading station configuration: {fname}")
                print(e)
                exit(1)

    main_conf['stations'] = sorted(stations, key=lambda station: station['channel_number'])

if 'stations' not in main_conf:
    load_json_stations()

