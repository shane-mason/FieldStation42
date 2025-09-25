from fs42.liquid_io import LiquidIO


class LiquidAPI:

    @staticmethod
    def add_blocks(station_config, blocks):
        LiquidIO().put_liquid_blocks(station_config["network_name"], blocks)

    @staticmethod
    def get_blocks(station_config, start=None, end=None):
        if not station_config:
            return None
        if not start and not end:
            return LiquidIO().get_liquid_blocks(station_config["network_name"])
        else:
            # If start and end are provided, filter the blocks accordingly
            return LiquidIO().query_liquid_blocks(station_config["network_name"], start, end)

    @staticmethod
    def delete_blocks(station_config):
        LiquidIO().delete_liquid_blocks(station_config["network_name"])

    @staticmethod
    def search_blocks(station_config, query: str):
        return LiquidIO().search_liquid_blocks(station_config["network_name"], query)

    @staticmethod
    def search_all_blocks(query: str):
        return LiquidIO().search_all_liquid_blocks(query)
