import logging
import sys
import argparse
import datetime
from rich.console import Console

from fs42.catalog import ShowCatalog
from fs42.station_manager import StationManager
from fs42.liquid_manager import LiquidManager
from fs42.liquid_schedule import LiquidSchedule
from fs42.fluid_builder import FluidBuilder
from fs42.sequence_api import SequenceAPI
from fs42.liquid_api import LiquidAPI
from fs42.catalog_api import CatalogAPI

FF_USE_FLUID_FILE_CACHE = True

logging.basicConfig(format="%(levelname)s:%(name)s:%(message)s", level=logging.INFO)


class Station42:
    def __init__(self, config, rebuild_catalog=False, force=False):
        # station configuration
        self.config = config
        self._l = logging.getLogger(self.config["network_name"])
        self.catalog: ShowCatalog = ShowCatalog(
            self.config, rebuild_catalog=rebuild_catalog, force=force
        )
        self.get_text_listing = self.catalog.get_text_listing
        self.check_catalog = self.catalog.check_catalog


def print_outcome(success_messages, failure_messages, console):
    console.print(
        "[bold blue underline]Finished running FieldStation42.[/bold blue underline]"
    )

    if len(success_messages) > 0:
        print("\n")
        console.print("[bold green underline]I had successes![/bold green underline]")
        for message in success_messages:
            console.print(f"[green]{message}[/green]")

    if len(failure_messages) > 0:
        print("\n")
        console.print("[bold red underline]I had failures:[/bold red underline]")
        for message in failure_messages:
            console.print(f"[red]{message}[/red]")


def build_parser():
    parser = argparse.ArgumentParser(
        description="FieldStation42 Catalog and Liquid-Schedule Generation"
    )
    parser.add_argument(
        "-g",
        "--graphical_interface",
        action="store_true",
        help="Run graphical interface to configure catalogs and schedules",
    )
    parser.add_argument(
        "-l", "--logfile", help="Set logging to use output file - will append each run"
    )
    parser.add_argument(
        "-c",
        "--check_catalogs",
        nargs="*",
        help="Check catalogs for the specified network names, print report and exit.",
    )
    parser.add_argument(
        "-p",
        "--printcat",
        help="Print the catalog for the specified network name and exit",
    )
    parser.add_argument(
        "-r",
        "--rebuild_catalog",
        nargs="*",
        help="Rebuild catalog for the specified network names or all networks if no parameter given",
    )
    parser.add_argument(
        "-q",
        "--rebuild_sequences",
        nargs="*",
        help="Restarts sequences for the named stations or all stations if none are specified. This will take effect in next schedule build.",
    )
    parser.add_argument(
        "-a",
        "--scan_sequences",
        nargs="*",
        help="Scan for new sequences that have been added to configurations for next schedule build.",
    )
    parser.add_argument(
        "-b",
        "--break_detect_dir",
        help="Scan for points break insertion point in media files in the provided directory. (VERY experimental)",
    )
    parser.add_argument(
        "-w",
        "--add_week",
        nargs="*",
        help="Add one week to the specifided stations, or all stations if none are specified.",
    )
    parser.add_argument(
        "-m",
        "--add_month",
        nargs="*",
        help="Add one month to the specified stations, or all stations if none are specified.",
    )
    parser.add_argument(
        "-d",
        "--add_day",
        nargs="*",
        help="Add one day to to the specified stations, or all stations if none are specified.",
    )
    parser.add_argument(
        "-e",
        "--schedule",
        action="store_true",
        help="View schedule summary information for all stations.",
    )
    parser.add_argument(
        "-u",
        "--print_schedule",
        help="Print schedule for current day for the specified network name",
    )
    parser.add_argument(
        "-x",
        "--delete_schedules",
        nargs="*",
        help="Delete the schedule for the specified network names or all networks if no parameter given",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="With -r or -x will force deletion of schedules and catalogs if they are failing. Wont reset sequences, file cache or breakpoints",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Set logging verbosity level to very chatty",
    )
    parser.add_argument(
        "-s", "--server",
        action="store_true",
        help="Run the FieldStation42 web API server after other actions.",
    )
    return parser


def main():
    _l = logging.getLogger("Station42")
    success_messages = []
    failure_messages = []
    console = Console(color_system="standard", force_terminal=True)

    def _get_arg_stations(args):
        nonlocal _l
        _rebuild_list = []
        if len(args) == 0:
            _rebuild_list = StationManager().stations
        else:
            for arg in args:
                conf = StationManager().station_by_name(arg)
                if conf:
                    _rebuild_list.append(StationManager().station_by_name(arg))
                else:
                    raise ValueError(f"Can't find station by name: {arg}")
        return _rebuild_list

    execution_start_time = datetime.datetime.now()
    parser = build_parser()
    args = parser.parse_args()

    if args.graphical_interface or len(sys.argv) <= 1:
        try:
            from fs42.ux.ux import StationApp
        except ModuleNotFoundError:
            _l.error("Could not load graphical interface - please install textual")
            _l.error("Use this command to install: pip install textual")
            sys.exit(-1)

        app = StationApp()
        app.run()
        sys.exit()

    if args.verbose:
        _l.setLevel(logging.DEBUG)
        success_messages.append("I enabled verbose logging")

    if args.logfile:
        formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s:%(message)s")
        fh = logging.FileHandler(args.logfile)
        fh.setFormatter(formatter)
        _l.addHandler(fh)
        success_messages.append(f"I setup logging to file: {args.logfile}")

    if args.schedule:
        _l.info("Printing shedule summary.")
        print(LiquidManager().get_summary())
        success_messages.append("I printed the schedule summary")
        print_outcome(success_messages, failure_messages, console)
        return
    elif args.printcat is not None:
        conf = StationManager().station_by_name(args.printcat)
        if conf:
            try:
                _l.info(f"Printing catalog for {conf['network_name']}")
                print(Station42(conf, False).get_text_listing())
                success_messages.append(
                    f"I printed the catalog for {conf['network_name']}"
                )
            except Exception as e:
                console.print(
                    f"[red]Error printing catalog for {conf['network_name']}: {e}[/red]"
                )
                _l.exception(e)
                failure_messages.append(
                    f"Failed to print catalog for {conf['network_name']} - check logs."
                )
        else:
            _l.error(f"Can't find station by name: {args.printcat}")
            failure_messages.append(
                f"Can't find station by name to print catalog: {args.printcat}"
            )
        print_outcome(success_messages, failure_messages, console)
        return
    elif args.print_schedule:
        try:
            LiquidManager().print_schedule(args.print_schedule, args.verbose)
            success_messages.append(f"I printed the schedule for {args.print_schedule}")
        except Exception as e:
            console.print(f"[red]Error printing schedule: {e}[/red]")
            _l.exception(e)
            failure_messages.append("Failed to print schedule - check logs.")
        print_outcome(success_messages, failure_messages, console)
        return
    elif args.check_catalogs is not None:
        _rebuild_list = []
        try:
            _rebuild_list = _get_arg_stations(args.check_catalogs)
        except Exception as e:
            console.print("[red]Error getting list of stations to rebuild: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to check catalogs - check your arguments."
            )

        for station in _rebuild_list:
            if station["_has_catalog"]:
                _l.info(f"Checking catalog for {station['network_name']}")
                try:
                    Station42(station, False, False).check_catalog()
                    success_messages.append(
                        f"Successfully checked catalog for {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error checking catalog for {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to check catalog for {station['network_name']} - check logs."
                    )
        print_outcome(success_messages, failure_messages, console)
        return

    if args.delete_schedules is not None:
        _l.info("Starting schedule deletions")
        _rebuild_list = []
        try:
            _rebuild_list = _get_arg_stations(args.delete_schedules)
        except Exception as e:
            console.print(f"[red]Error getting list of stations to delete: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to delete schedules - check your arguments."
            )

        for station in _rebuild_list:
            if station["_has_schedule"]:
                _l.info(f"Deleting schedule for {station['network_name']}")

                try:
                    if args.force:
                        LiquidAPI.delete_blocks(station)
                    else:
                        LiquidManager().reset_schedule(station, args.force)
                    success_messages.append(
                        f"Successfully deleted schedule for {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error deleting schedule for {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to delete schedule for {station['network_name']} - check logs."
                    )

    if args.rebuild_catalog is not None:
        _rebuild_list = []
        _l.info("Starting catalog rebuild.")
        try:
            _rebuild_list = _get_arg_stations(args.rebuild_catalog)
        except Exception as e:
            console.print(f"[red]Error getting list of stations to rebuild: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to rebuild - check your arguments."
            )

        for station in _rebuild_list:
            if station["_has_catalog"]:
                _l.info(f"Building catalog for {station['network_name']}")
                try:
                    Station42(station, True, args.force)
                    success_messages.append(
                        f"Successfully built catalog for {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error building catalog for {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to build catalog for {station['network_name']} - check logs."
                    )

        if FF_USE_FLUID_FILE_CACHE:
            try:
                FluidBuilder().trim_file_cache(execution_start_time)
                success_messages.append("I trimmed the fluid cache")
            except Exception as e:
                console.print(f"[red]Error trimming fluid cache: {e}[/red]")
                _l.exception(e)
                failure_messages.append("Failed to trim fluid cache - check logs.")

    if args.scan_sequences is not None:
        _rebuild_list = []
        try:
            _rebuild_list = _get_arg_stations(args.scan_sequences)
        except Exception as e:
            console.print(f"[red]Error getting list of stations to scan: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to scan sequences - check your arguments."
            )

        for station in _rebuild_list:
            if station["_has_catalog"]:
                _l.info(f"Scanning for new sequences for {station['network_name']}")
                try:
                    SequenceAPI.scan_sequences(station)
                    success_messages.append(
                        f"Successfully scanned for new sequences for {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error scanning for new sequences for {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to scan for new sequences for {station['network_name']} - check logs."
                    )
                

    if args.rebuild_sequences is not None:
        _rebuild_list = []
        try:
            _rebuild_list = _get_arg_stations(args.rebuild_sequences)
        except Exception as e:
            console.print(f"[red]Error getting list of stations to rebuild: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to rebuild sequences - check your arguments."
            )

        for station in _rebuild_list:
            if station["_has_catalog"]:
                _l.info(f"Rebuilding sequences for {station['network_name']}")
                try:
                    SequenceAPI.rebuild_sequences(station)
                    success_messages.append(
                        f"Successfully rebuilt sequences for {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error rebuilding sequences for {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to rebuild sequences for {station['network_name']} - check logs."
                    )

    if args.break_detect_dir is not None:
        _l.info("Scanning for break detection points in media files...")
        FluidBuilder().scan_breaks(args.break_detect_dir)
        success_messages.append("I scanned for break detection points")

    if args.add_day is not None:
        _to_add_to = []
        try:
            _to_add_to = _get_arg_stations(args.add_day)
        except Exception as e:
            console.print(f"[red]Error getting list of stations to add days: {e}[/red]")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to add days - check your arguments."
            )

        for station in _to_add_to:
            if station["_has_schedule"]:
                try:
                    liquid = LiquidSchedule(station)
                    liquid.add_days(1)
                    success_messages.append(
                        f"I added a day to {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error adding a day to {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)

                    failure_messages.append(
                        f"Failed to add a day to {station['network_name']} - check logs."
                    )

    if args.add_week is not None:
        _to_add_to = []
        try:
            _to_add_to = _get_arg_stations(args.add_week)
        except Exception as e:
            _l.error(f"Error getting list of stations to add weeks: {e}")
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to add weeks - check your arguments."
            )

        for station in _to_add_to:
            if station["_has_schedule"]:
                try:
                    liquid = LiquidSchedule(station)
                    liquid.add_week()
                    success_messages.append(
                        f"I added a week to {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error adding a week to {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to add a week to {station['network_name']} - check logs."
                    )

    if args.add_month is not None:
        _to_add_to = []
        try:
            _to_add_to = _get_arg_stations(args.add_month)
        except Exception as e:
            console.print(
                f"[red]Error getting list of stations to add months: {e}[/red]"
            )
            _l.exception(e)
            failure_messages.append(
                "Failed to get list of stations to add months - check your arguments."
            )

        for station in _to_add_to:
            if station["_has_schedule"]:
                try:
                    liquid = LiquidSchedule(station)
                    liquid.add_month()
                    success_messages.append(
                        f"I added a month to {station['network_name']}"
                    )
                except Exception as e:
                    console.print(
                        f"[red]Error adding a month to {station['network_name']}: {e}[/red]"
                    )
                    _l.exception(e)
                    failure_messages.append(
                        f"Failed to add a month to {station['network_name']} - check logs."
                    )

    if args.server:
        try:
            from fs42.fs42_server.fs42_server import mount_fs42_api
        except ImportError:
            console.print("[red]Could not import mount_fs42_api from fs42_server.py[/red]")
            sys.exit(-1)
        mount_fs42_api()
        return

    print_outcome(success_messages, failure_messages, console)


if __name__ == "__main__":
    main()
