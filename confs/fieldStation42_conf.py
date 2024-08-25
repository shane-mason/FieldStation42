from confs import nbc_conf, abc_conf, pbs_conf, cbs_conf

main_conf = {
    'stations' : [nbc_conf.station_conf, abc_conf.station_conf, pbs_conf.station_conf, cbs_conf.station_conf],
    'channel_socket' : "runtime/channel.socket"
}
