import logging
import sys

from fs42.catalog import ShowCatalog
from fs42.station_manager import StationManager
from fs42.liquid_manager import LiquidManager
from fs42.liquid_schedule import LiquidSchedule

import argparse

logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)

class Station42:

    def __init__(self, config, rebuild_catalog=False):
        # station configuration
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        self.catalog:ShowCatalog = ShowCatalog(self.config, rebuild_catalog=rebuild_catalog)
        self.get_text_listing = self.catalog.get_text_listing
        self.check_catalog = self.catalog.check_catalog

def main():

    parser = argparse.ArgumentParser(description='FieldStation42 Catalog and Liquid-Schedule Generation')
    parser.add_argument('-g', '--graphical_interface', action='store_true', help='Run graphical interface to configure catalogs and schedules')
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument('-c', '--check_catalogs', action='store_true', help='Check catalogs, print report and exit.')
    parser.add_argument('-p', '--printcat', help='Print the catalog for the specified network name and exit')
    parser.add_argument('-r', '--rebuild_catalog', action='store_true', help='Rebuild catalogs and schedules')
    parser.add_argument('-q', '--rebuild_sequences', action='store_true', help='Restarts all sequences - will take effect in next schedule build.')
    parser.add_argument('-a', '--scan_sequences', action='store_true', help='Scan for new sequences that have been added to configurations for next schedule build.')
    parser.add_argument('-w', '--add_week', action='store_true', help='Add one week to all schedules' )
    parser.add_argument('-m', '--add_month', action='store_true', help='Add one month to all schedules' )
    parser.add_argument('-d', '--add_day', action='store_true', help='Add one day to all schedules' )
    parser.add_argument('-s', '--schedule', action='store_true', help='View schedule summary information for all stations.' )
    parser.add_argument('-u', '--print_schedule', help='Print schedule for current day for the specified network name' )
    parser.add_argument('-x', '--delete_schedules', action='store_true', help='Delete all schedules (but not catalogs)' )
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')

    args = parser.parse_args()

    if args.graphical_interface or len(sys.argv) <= 1:
        try:
            from fs42.ux.ux import StationApp
        except ModuleNotFoundError:
            logging.getLogger().error(f"Could not load graphical interface - please install textual")
            logging.getLogger().error(f"Use this command to install: pip install textual")
            sys.exit(-1)

        app = StationApp()
        app.run()
        sys.exit()

    if( args.verbose ):
        logging.getLogger().setLevel(logging.DEBUG)

    if (args.logfile):
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    if args.schedule:
        logging.getLogger().info("Printing shedule summary.")
        print(LiquidManager().get_summary())
        return
    



    if args.delete_schedules:
        logging.getLogger().info("Deleting all schedules")
        LiquidManager().reset_all_schedules()
        logging.getLogger().info("All schedules deleted")

    if args.print_schedule:
        LiquidManager().print_schedule(args.print_schedule, args.verbose)
        return

    sm = StationManager()
    found_print_target = False
    processed_catalog_paths = set() # Initialize set to track processed catalog paths

    for station_conf in sm.stations:
        if station_conf['network_type'] == 'guide':
            #catch guide so we don't print it or try to further process
            logging.getLogger().info("Loading and checking guide channel")
            from fs42.guide_tk import GuideWindowConf
            gconf = GuideWindowConf()
            errors = gconf.check_config(station_conf)
            if len(errors):
                logging.getLogger().error("Errors found in Guide Channel configuration:")
                for err in errors:
                    logging.getLogger().error(err)
                logging.getLogger().error("Please check your configuration and try agian.")
                exit(-1)
            else:
                logging.getLogger().info("Guide channel checks completed.")
        elif args.printcat:
            if station_conf['network_name'] == args.printcat:
                logging.getLogger().info(f"Printing catalog for {station_conf['network_name']}")
                print(Station42(station_conf, args.rebuild_catalog).get_text_listing())
                found_print_target = True
        else:
            rebuild_flag_for_this_station = args.rebuild_catalog
            catalog_path = station_conf.get('catalog_path')
            if args.rebuild_catalog:
                if catalog_path:
                    if catalog_path in processed_catalog_paths:
                        logging.getLogger().info(
                            f"Catalog for path '{catalog_path}' (network: {station_conf['network_name']}) "
                            f"has already been processed in this run. Skipping redundant rebuild."
                        )
                        rebuild_flag_for_this_station = False
                    else:
                        # This catalog path will be processed (rebuilt or loaded if rebuild fails but path is new)
                        processed_catalog_paths.add(catalog_path)
                else:
                    logging.getLogger().warning(
                        f"Station '{station_conf['network_name']}' does not have a 'catalog_path' defined. "
                        f"It will be rebuilt if --rebuild_catalog is set, but cannot share a catalog."
                    )
            

            logging.getLogger().info(f"Processing station: {station_conf['network_name']}")
            station = Station42(station_conf, rebuild_flag_for_this_station)

            if args.rebuild_sequences:
                station.catalog.rebuild_sequences(True)
            elif args.scan_sequences:
                station.catalog.scan_sequences(True)

            if args.check_catalogs:
                #then just run a check and exit
                logging.getLogger().info(f"Checking catalog for {station_conf['network_name']}")
                station.check_catalog()
            else:
                logging.getLogger().info(f"Checking for schedule tasks for {station_conf['network_name']}")
                #schedule = station.make_weekly_schedule()
                liquid = LiquidSchedule(station_conf)
                if args.add_day:
                    liquid.add_days(1)
                elif args.add_week:
                    liquid.add_week()
                elif args.add_month:
                    liquid.add_month()
                else:
                    logging.getLogger().info("No schedules generated, use -h --help to see available options")

    if args.printcat and not found_print_target:
        logging.getLogger().error(f"Could not find catalog for network named: {args.printcat}")

if __name__ == "__main__":
    main()




