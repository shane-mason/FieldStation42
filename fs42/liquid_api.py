from fs42.liquid_io import LiquidIO


class LiquidAPI:
    @staticmethod
    def set_blocks(station_config, blocks):
        LiquidIO().put_liquid_blocks(station_config["network_name"], blocks)

    @staticmethod
    def add_blocks(station_config, blocks):
        pass

    @staticmethod
    def get_blocks(station_config):
        return LiquidIO().get_liquid_blocks(station_config["network_name"])

    @staticmethod
    def delete_blocks(station_config):
        LiquidIO().delete_liquid_blocks(station_config["network_name"])
