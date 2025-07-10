from fs42.catalog_io import CatalogIO
from fs42.catalog_entry import CatalogEntry


class CatalogAPI:
    @staticmethod
    def delete_catalog(station_config):
        CatalogIO().delete_all_entries_for_station(station_config["network_name"])

    @staticmethod
    def set_entries(station_config, entries: list[CatalogEntry]):
        CatalogAPI.delete_catalog(station_config)
        CatalogIO().put_catalog_entries(station_config["network_name"], entries)

    @staticmethod
    def get_entries(station_config):
        return CatalogIO().get_catalog_entries(station_config["network_name"])

    @staticmethod
    def get_by_tag(station_config, tag):
        return CatalogIO().get_by_tag(station_config["network_name"], tag)

    @staticmethod
    def get_by_path(station_config, path):
        return CatalogIO().get_entry_by_path(station_config["network_name"], path)

    @staticmethod
    def update_play_counts(station_config, entries: list[CatalogEntry]):
        # flatten the entries list
        flat = []
        for entry in entries:
            if isinstance(entry, list):
                flat.extend(entry)
            else:
                flat.append(entry)
        CatalogIO().batch_increment_counts(station_config["network_name"], flat)

    @staticmethod
    def get_entry_by_id(entry_id):
        return CatalogIO().entry_by_id(entry_id)
