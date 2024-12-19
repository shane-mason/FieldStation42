import argparse
import time
import datetime
import json
import signal
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)

from confs.fieldStation42_conf import main_conf
from fs42.station_manager import StationManager
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2
from fs42.station_player import StationPlayer, PlayStatus
from fs42.reception import ReceptionStatus

#from fs42.guide_channel import guide_channel_runner, GuideCommands

debounce_fragment = 0.05

def main_loop(transition_fn):
    manager = StationManager()
    reception = ReceptionStatus()
    logger = logging.getLogger("MainLoop")
    logger.info("Starting main loop")

    channel_socket = main_conf['channel_socket']
    #go ahead and clear the channel socket (or create if it doesn't exist)
    with open(channel_socket, 'w'):
        pass

    channel_index = 0
    if not len(manager.stations):
        logger.error("Could not find any station runtimes - do you have your channels configured?")
        logger.error("Check to make sure you have valid json configurations in the confs dir")
        logger.error("The confs/examples folder contains working examples that you can build off of - just move one into confs/")
        return

    player = StationPlayer(manager.stations[channel_index])
    reception.degrade()
    player.update_filters()


    def sigint_handler(sig, frame):

        logger.critical("Recieved sig-int signal, attempting to exit gracefully...")
        player.shutdown()
        logger.critical("Shutdown is complete - exiting application")
        exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    channel_conf = manager.stations[channel_index]
    while True:
        logger.info(f"Playing station: {channel_conf['network_name']}" )
        outcome = None

        # is this the guide channel?
        if  channel_conf["network_type"] == "guide":
            logger.info("Starting the guide channel")
            outcome = player.show_guide(channel_conf)
        else:
            now = datetime.datetime.now()
            week_day = DAYS[now.weekday()]
            hour = now.hour
            skip = now.minute * MIN_1 + now.second
            #skip = 60 * 59
            logger.info(f"Starting station {channel_conf['network_name']} at: {week_day} {hour} skipping={skip} ")
            outcome = player.play_slot(week_day, hour, skip, runtime_path=channel_conf["runtime_dir"])


        if outcome.status == PlayStatus.CHANNEL_CHANGE:
            tune_up = True
            #get the json payload
            if outcome.payload:
                try:
                    as_obj = json.loads(outcome.payload)
                    if "command" in as_obj and as_obj["command"] == "direct":
                        if "channel" in as_obj:
                            logger.info(f"Got direct tune command for channel {as_obj['channel']}")
                            new_index = manager.index_from_channel(as_obj['channel'])
                            if not new_index:
                                logger.error(f"Got direct tune command but could not find station with channel {as_obj['channel']}")
                            else:
                                channel_index = new_index
                                tune_up = False
                        else:
                            logger.critical("Got direct tune command, but no channel specified")
                except Exception as e:
                    logger.exception(e)
                    logger.warning("Got payload on channel change, but JSON convert failed")


            if tune_up:
                logger.info("Starting channel change")
                channel_index+=1
                if channel_index>=len(manager.stations):
                    channel_index = 0
                
            channel_conf = manager.stations[channel_index]
            
            #long_change_effect(player, reception)
            transition_fn(player, reception)

        elif outcome.status == PlayStatus.EXITED:
            logger.critical("Player exited - resting for 1 second and trying again")
            time.sleep(1)

def none_change_effect(player, reception):
    pass

def short_change_effect(player, reception ):
    while not reception.is_fully_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)
    
def long_change_effect(player, reception):
    #add noise to current channel
    while not reception.is_fully_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)

    #reception.improve(1)
    player.play_file("runtime/static.mp4")
    while not reception.is_perfect():
        reception.improve()
        player.update_filters()
        time.sleep(debounce_fragment)
    #time.sleep(1)
    while not reception.is_fully_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='FieldStation42 Player')
    parser.add_argument('-t', '--transition', choices=["long", "short", "none"], help='Transition effect to use on channel change')
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')
    args = parser.parse_args()

    if(args.verbose):
        logging.getLogger().setLevel(logging.DEBUG)

    if(args.logfile):
        print("will be logging ", args.logfile)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    trans_fn = short_change_effect
    if args.transition:
        if args.transition == "long":
            trans_fn = long_change_effect
            ReceptionStatus().degrade_amount = 0.04
            ReceptionStatus().improve_amount = 0.1
        elif args.transition == "none":
            trans_fn = none_change_effect
        #else keep short change as default
        

    main_loop(trans_fn)
