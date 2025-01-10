import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)
import datetime
import os
from fs42.catalog import ShowCatalog
from fs42.station_manager import StationManager
from fs42.liquid_manager import LiquidManager
from fs42.liquid_schedule import LiquidSchedule
import argparse

class Station42:

    def __init__(self, config, rebuild_catalog=False):
        # station configuration
        self.config = config
        self._l = logging.getLogger(self.config['network_name'])
        self.catalog:ShowCatalog = ShowCatalog(self.config, rebuild_catalog=rebuild_catalog)
        self.print_catalog = self.catalog.print_catalog
        self.check_catalog = self.catalog.check_catalog

def main():

    parser = argparse.ArgumentParser(description='FieldStation42 Catalog and Liquid-Schedule Generation')
    parser.add_argument('-c', '--check_catalogs', action='store_true', help='Check catalogs, print report and exit.')
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument('-p', '--printcat', help='Print the catalog for the specified network name and exit')
    parser.add_argument('-r', '--rebuild_catalog', action='store_true', help='Rebuild catalogs and schedules')
    parser.add_argument('-w', '--add_week', action='store_true', help='Add one week to all schedules' )
    parser.add_argument('-m', '--add_month', action='store_true', help='Add one month to all schedules' )
    parser.add_argument('-d', '--add_day', action='store_true', help='Add one day to all schedules' )
    parser.add_argument('-s', '--schedule', action='store_true', help='Initialize and align schedules across all stations.' )
    parser.add_argument('-u', '--print_schedule', help='Print network schedule for current day (for debugging)' )
    parser.add_argument('-x', '--delete_schedules', action='store_true', help='Delete all schedules (but not catalogs)' )
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')

    args = parser.parse_args()

    if( args.verbose ):
        logging.getLogger().setLevel(logging.DEBUG)

    if (args.logfile):
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)

    if args.schedule:
        logging.getLogger().info(f"Printing shedule summary.")
        print(LiquidManager().get_summary())
        return
    
    if args.delete_schedules:
        logging.getLogger().info(f"Deleting all schedules")
        for station in StationManager().stations:
            if station['network_type'] != "guide":
                if os.path.exists(station["schedule_path"]):
                    os.unlink(station["schedule_path"])
        logging.getLogger().info(f"All schedules deleted")
        return

    if args.print_schedule:
        LiquidManager().print_schedule(args.print_schedule, datetime.datetime.now())
        return

    found_print_target = False

    for station_conf in StationManager().stations:
        if station_conf['network_type'] == "guide":
            #catch guide so we don't print it or try to further process
            logging.getLogger().info(f"Loaded guide channel")
        elif args.printcat:
            if station_conf['network_name'] == args.printcat:
                logging.getLogger().info(f"Printing catalog for {station_conf['network_name']}")
                Station42(station_conf, args.rebuild_catalog).print_catalog()
                found_print_target = True
        else:
            logging.getLogger().info(f"Loading catalog for {station_conf['network_name']}")
            station = Station42(station_conf, args.rebuild_catalog)
            if args.check_catalogs:
                #then just run a check and exit
                logging.getLogger().info(f"Checking catalog for {station_conf['network_name']}")
                station.check_catalog()
            else:
                logging.getLogger().info(f"Making schedule for {station_conf['network_name']}")
                #schedule = station.make_weekly_schedule()
                liquid = LiquidSchedule(station_conf)
                if args.add_day:
                    liquid.add_days(1)
                elif args.add_week:
                    liquid.add_week()
                elif args.add_month:
                    liquid.add_month()
                else:
                    logging.getLogger().error("Nothing to do - use -h --help to see options")

    if args.printcat and not found_print_target:
        logging.getLogger().error(f"Could not find catalog for network named: {args.printcat}")

if __name__ == "__main__":
    main()




