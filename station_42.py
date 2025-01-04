import logging
logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)

from fs42.catalog import ShowCatalog
from fs42.timings import MIN_1, MIN_5, HOUR, H_HOUR, DAYS, HOUR2, OPERATING_HOURS
from fs42.station_manager import StationManager
import pickle
import json
import os
import glob
import random
import datetime
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
    parser.add_argument('-x', '--delete_schedules', help='Delete schedules (not catalogs)' )
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')

    args = parser.parse_args()

    if( args.verbose ):
        logging.getLogger().setLevel(logging.DEBUG)

    if (args.logfile):
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)

        logging.getLogger().addHandler(fh)


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
        elif args.delete_schedules:
            pass
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



    if args.printcat and not found_print_target:
        logging.getLogger().error(f"Could not find catalog for network named: {args.printcat}")

if __name__ == "__main__":
    main()




