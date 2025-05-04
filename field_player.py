import argparse
import time
import datetime
import json
import signal
import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(name)s:%(message)s', level=logging.INFO)

from fs42.station_manager import StationManager
from fs42.timings import MIN_1, DAYS
from fs42.station_player import StationPlayer, PlayStatus, check_channel_socket, update_status_socket
from fs42.reception import ReceptionStatus


debounce_fragment = 0.1

def main_loop(transition_fn):
    manager = StationManager()
    reception = ReceptionStatus()
    logger = logging.getLogger("MainLoop")
    logger.info("Starting main loop")

    channel_socket = StationManager().server_conf['channel_socket']

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

        logger.critical("Received sig-int signal, attempting to exit gracefully...")
        player.shutdown()

        update_status_socket("stopped", "", -1)
        logger.info("Shutdown completed as expected - exiting application")
        exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    channel_conf = manager.stations[channel_index]
    recheck_channel = False

    # this is actually the main loop
    outcome = None
    skip_play = False
    stuck_timer = 0

    while True:
        logger.info(f"Playing station: {channel_conf['network_name']}" )
        update_status_socket("playing", channel_conf['network_name'], channel_conf['channel_number']) 
       
        if  channel_conf["network_type"] == "guide" and not skip_play:
            logger.info("Starting the guide channel")
            outcome = player.show_guide(channel_conf)
        elif not skip_play:
            now = datetime.datetime.now()
            
            week_day = DAYS[now.weekday()]
            hour = now.hour
            skip = now.minute * MIN_1 + now.second
            
            logger.info(f"Starting station {channel_conf['network_name']} at: {week_day} {hour} skipping={skip} ")
            
            outcome = player.play_slot(channel_conf['network_name'],datetime.datetime.now())

        logger.debug(f"Got player outcome:{outcome.status}")

        # reset skip
        skip_play = False

        if outcome.status == PlayStatus.CHANNEL_CHANGE:
            stuck_timer = 0
            tune_up = True
            #get the json payload
            if outcome.payload:
                try:
                    as_obj = json.loads(outcome.payload)
                    if "command" in as_obj:
                        if as_obj["command"] == "direct":
                            tune_up = False
                            if "channel" in as_obj:
                                logger.debug(f"Got direct tune command for channel {as_obj['channel']}")
                                new_index = manager.index_from_channel(as_obj['channel'])
                                if new_index is None:
                                    logger.warning(f"Got direct tune command but could not find station with channel {as_obj['channel']}")
                                else:
                                    channel_index = new_index
                            else:
                                logger.critical("Got direct tune command, but no channel specified")
                        elif as_obj["command"] == "up":
                            tune_up = True
                            logger.debug(f"Got channel up command")
                        elif as_obj["command"] == "down":
                            tune_up = False
                            logger.debug(f"Got channel down command")
                            channel_index-=1
                            if channel_index<0:
                                channel_index = len(manager.stations)-1
                                        
                    
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

        elif outcome.status == PlayStatus.FAILED:
            
            stuck_timer+=1
            
            #only put it up once after 2 seconds of being stuck
            if stuck_timer == 2 and "standby_image" in channel_conf:
                player.play_file(channel_conf["standby_image"])
                
            update_status_socket("stuck", channel_conf['network_name'], channel_conf['channel_number'])

            time.sleep(1)
            logger.critical("Player failed to start - resting for 1 second and trying again")
            
            # check for channel change so it doesn't stay stuck on a broken channel
            new_outcome = check_channel_socket()
            if new_outcome is not None:
                outcome = new_outcome
                # set skip play so outcome isn't overwritten 
                # and the channel change can be processed next loop
                skip_play = True
        elif outcome.status == PlayStatus.SUCCESS:
            stuck_timer = 0
        else:
            stuck_timer = 0

        
def none_change_effect(player, reception):
    pass

def short_change_effect(player, reception ):
    prev = reception.improve_amount
    reception.improve_amount = 0

    while not reception.is_degraded():
        reception.degrade(.2)
        player.update_filters()
        time.sleep(debounce_fragment)
    
    reception.improve_amount = prev

def long_change_effect(player, reception):
    #add noise to current channel
    while not reception.is_degraded():
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
    while not reception.is_degraded():
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
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    trans_fn = short_change_effect

    if args.transition:
        if args.transition == "long":
            trans_fn = long_change_effect
        elif args.transition == "none":
            trans_fn = none_change_effect
        #else keep short change as default
        

    main_loop(trans_fn)
