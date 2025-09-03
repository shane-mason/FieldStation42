import multiprocessing
from queue import Empty
import argparse
import time
import datetime
import json
import signal
import logging

from fs42.liquid_manager import LiquidManager
from fs42.station_manager import StationManager
from fs42.timings import MIN_1, DAYS
from fs42.station_player import (
    StationPlayer,
    PlayerState,
    PlayerOutcome,
    update_status_socket,
)
from fs42.reception import (
    ReceptionStatus,
    long_change_effect,
    short_change_effect,
    none_change_effect,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO
)

try:
    from fs42.overlay.ticker import run_ticker
except ModuleNotFoundError:
    logging.getLogger("FieldPlayer").warning("Error importing ticker - using the ticker will cause an error.")

api_commands_queue: multiprocessing.Queue = None


def input_check():
    if api_commands_queue:
        q_message = None
        try:
            q_message = api_commands_queue.get(block=False)
        except Empty:
            pass
        
        if q_message:
            command = q_message.get("command", None)
            if not command:
                return
            match command:
                case "exit":
                    return PlayerOutcome(PlayerState.EXIT_COMMAND)
                case "reload_data":
                    LiquidManager().reload_schedules()
                case "guide":
                    c_number = StationManager().guide_config["channel_number"]
                    change_request = {"command": "direct", "channel": c_number}
                    return PlayerOutcome(PlayerState.CHANNEL_CHANGE, json.dumps(change_request))
                case "ticker":
                    message = q_message.get("message", None)
                    header = q_message.get("header", None)
                    style = q_message.get("style", None)
                    iterations = q_message.get("iterations", None)
                    run_ticker(message, header, style, iterations)

    channel_socket = StationManager().server_conf["channel_socket"]
    with open(channel_socket, "r") as r_sock:
        contents = r_sock.read()
    if len(contents):
        with open(channel_socket, "w"):
            pass
        return PlayerOutcome(PlayerState.CHANNEL_CHANGE, contents)
    return None


def main_loop(transition_fn, shutdown_queue=None, api_proc=None):
    manager = StationManager()
    reception = ReceptionStatus()
    logger = logging.getLogger("MainLoop")
    logger.info("Starting main loop")

    channel_socket = StationManager().server_conf["channel_socket"]

    # go ahead and clear the channel socket (or create if it doesn't exist)
    with open(channel_socket, "w"):
        pass

    channel_index = 0
    if not len(manager.stations):
        logger.error(
            "Could not find any station runtimes - do you have your channels configured?"
        )
        logger.error(
            "Check to make sure you have valid json configurations in the confs dir"
        )
        logger.error(
            "The confs/examples folder contains working examples that you can build off of - just move one into confs/"
        )
        return

    player = StationPlayer(manager.stations[channel_index], input_check)
    reception.degrade()
    player.update_filters()

    def sigint_handler(sig, frame):
        logger.critical("Received sig-int signal, attempting to exit gracefully...")
        player.shutdown()

        update_status_socket("stopped", "", -1)
        # Signal API server to shutdown if running
        if shutdown_queue is not None:
            shutdown_queue.put("shutdown")
        if api_proc is not None:
            api_proc.join(timeout=5)
        logger.info("Shutdown completed as expected - exiting application")
        exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    channel_conf = manager.stations[channel_index]

    # this is actually the main loop
    player_state = None
    skip_play = False
    stuck_timer = 0

    while True:
        logger.info(f"Playing station: {channel_conf['network_name']}")

        if channel_conf["network_type"] == "guide" and not skip_play:
            logger.info("Starting the guide channel")
            player_state = player.show_guide(channel_conf)
        elif channel_conf["network_type"] == "web" and not skip_play:
            logger.info("Starting the web channel")
            player_state = player.show_web(channel_conf)
        elif not skip_play:
            now = datetime.datetime.now()

            week_day = DAYS[now.weekday()]
            hour = now.hour
            skip = now.minute * MIN_1 + now.second

            logger.info(
                f"Starting station {channel_conf['network_name']} at: {week_day} {hour} skipping={skip} "
            )

            player_state = player.play_slot(
                channel_conf["network_name"], datetime.datetime.now()
            )

        logger.debug(f"Got player outcome:{player_state.status}")

        # reset skip
        skip_play = False

        if player_state.status == PlayerState.CHANNEL_CHANGE:
            stuck_timer = 0
            # Cache stations to prevent race conditions during reload
            station_cache = manager.stations
            stations_len = len(station_cache)
            #if we got anything, we'll tune up one channel
            tune_up = True
            # get the json payload
            if player_state.payload:
                try:
                    as_obj = json.loads(player_state.payload)
                    if "command" in as_obj:
                        if as_obj["command"] == "direct":
                            tune_up = False
                            if "channel" in as_obj:
                                logger.debug(
                                    f"Got direct tune command for channel {as_obj['channel']}"
                                )
                                new_index = manager.index_from_channel(
                                    as_obj["channel"]
                                )
                                if new_index is None:
                                    logger.warning(
                                        f"Got direct tune command but could not find station with channel {as_obj['channel']}"
                                    )
                                else:
                                    channel_index = new_index
                            else:
                                logger.critical(
                                    "Got direct tune command, but no channel specified"
                                )
                        elif as_obj["command"] == "up":
                            tune_up = True
                            logger.debug("Got channel up command")
                        elif as_obj["command"] == "down":
                            tune_up = False
                            logger.debug("Got channel down command")
                            found = False
                            while not found:
                                channel_index -= 1
                                # channel_index = channel_index if channel_index >= 0 else len(manager.stations)-1
                                if channel_index < 0:
                                    channel_index = stations_len-1
                                if not station_cache[channel_index]["hidden"]:
                                    found = True

                except Exception as e:
                    logger.exception(e)
                    logger.warning(
                        "Got payload on channel change, but JSON convert failed"
                    )

            if tune_up:
                logger.info("Starting channel change")
                found = False
                while not found:
                    channel_index += 1
                    channel_index = channel_index if channel_index < stations_len else 0
                    found = not station_cache[channel_index]["hidden"]


            channel_conf = station_cache[channel_index]
            player.station_config = channel_conf

            # long_change_effect(player, reception)
            transition_fn(player, reception)

        elif player_state.status == PlayerState.FAILED:
            stuck_timer += 1

            # only put it up once after 2 seconds of being stuck
            if stuck_timer >= 2 and "standby_image" in channel_conf:
                player.play_file(channel_conf["standby_image"])
            current_title_on_stuck = player.get_current_path()
            update_status_socket(
                "stuck",
                channel_conf["network_name"],
                channel_conf["channel_number"],
                current_title_on_stuck,
            )

            time.sleep(1)
            logger.critical(
                "Player failed to start - resting for 1 second and trying again"
            )

            # check for channel change so it doesn't stay stuck on a broken channel
            new_state = input_check()
            if new_state is not None:
                player_state = new_state
                # set skip play so outcome isn't overwritten
                # and the channel change can be processed next loop
                skip_play = True
        elif player_state.status == PlayerState.SUCCESS:
            stuck_timer = 0
        elif player_state.status == PlayerState.EXIT_COMMAND:
            sigint_handler(None, None)
        else:
            stuck_timer = 0


def start_api_server_with_shutdown_queue(shutdown_queue, command_q):
    from fs42.fs42_server import fs42_server

    fs42_server.run_with_shutdown_queue(shutdown_queue, command_q)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FieldStation42 Player")
    parser.add_argument(
        "-t",
        "--transition",
        choices=["long", "short", "none"],
        help="Transition effect to use on channel change",
    )
    parser.add_argument(
        "-l", "--logfile", help="Set logging to use output file - will append each run"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Set logging verbosity level to very chatty",
    )

    parser.add_argument(
        "--no_server",
        action="store_true",
        help="Do not start the web API server process.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.logfile:
        formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s:%(message)s")
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    trans_fn = short_change_effect

    if args.transition:
        if args.transition == "long":
            trans_fn = long_change_effect
        elif args.transition == "none":
            trans_fn = none_change_effect
        # else keep short change as default

    if not args.no_server:
        # Set up shutdown queue and start API server as a background process
        shutdown_queue = multiprocessing.Queue()
        api_commands_queue = multiprocessing.Queue()
        api_proc = multiprocessing.Process(
            target=start_api_server_with_shutdown_queue,
            args=(
                shutdown_queue,
                api_commands_queue,
            ),
            daemon=True,
        )
        api_proc.start()
    else:
        shutdown_queue = None
        api_commands_queue = None
        api_proc = None

    try:
        main_loop(trans_fn, shutdown_queue=shutdown_queue, api_proc=api_proc)
    finally:
        if shutdown_queue is not None:
            shutdown_queue.put("shutdown")
        if api_proc is not None:
            api_proc.join(timeout=5)
