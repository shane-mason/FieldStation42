import logging
from fs42.timings import DAYS
from fs42.sequence_io import SequenceIO
from fs42.media_processor import MediaProcessor
from fs42.sequence import NamedSequence, SequenceEntry

class SequenceAPI:

    @staticmethod
    def get_next_in_sequence(station_config, sequence_name, tag_path) -> SequenceEntry:
        _l = logging.getLogger("SEQUENCE")
        sio = SequenceIO()
        seq = sio.get_sequence(station_config["network_name"], sequence_name, tag_path)
        next_entry = None

        if not seq:
            _l.error(f"Sequence {sequence_name} for {station_config['network_name']} not found.")
            return None

        if seq.current_index < seq.start_index or seq.current_index >= seq.end_index:
            _l.info(f"Current index {seq.current_index} is out of bounds for sequence {sequence_name}. Resetting to start.")
            seq.current_index = seq.start_index
        
        next_entry = seq.episodes[seq.current_index]
        seq.current_index += 1
        
        sio.put_sequence(station_config["network_name"], seq)
        
        return next_entry

    @staticmethod
    def delete_sequences(station_config):
        _l = logging.getLogger("SEQUENCE")
        _l.debug(f"Deleting sequences for {station_config['network_name']}")
        sio = SequenceIO()
        sio.delete_sequences_for_station(station_config["network_name"])
        _l.debug(f"Deleted sequences for {station_config['network_name']}")

    @staticmethod
    def rebuild_sequences(station_config):
        _l = logging.getLogger("SEQUENCE")
        _l.debug(f"Rebuilding sequences for {station_config['network_name']}")
        SequenceAPI.delete_sequences(station_config)
        SequenceAPI.scan_sequences(station_config)
        _l.debug(f"Rebuilt sequences for {station_config['network_name']}")
    
    @staticmethod
    def scan_sequences(station_config):
        for day in DAYS:
            if day in station_config:
                slots = station_config[day]
                for k in slots:
                    if "sequence" in slots[k]:
                        # the user supplied sequence name
                        if isinstance(slots[k]["tags"], list):
                            for tag in slots[k]["tags"]:
                                SequenceAPI._build_sequence(station_config, tag, slots[k])
                        else:
                            SequenceAPI._build_sequence(station_config, slots[k]["tags"], slots[k])

    @staticmethod
    def _build_sequence(station_config, this_tag, slot):
        _l = logging.getLogger("SEQUENCE")
        seq_tag = this_tag
        seq_name = slot["sequence"]


        if seq_tag in station_config["clip_shows"]:
            _l.error(
                f"Schedule logic error in {station_config['network_name']}: Clip shows are not currently supported as sequences"
            )
            _l.error(
                f"{seq_tag} is in the clip shows list, but is declared as a sequence on {this_tag} as {seq_name}"
            )
            raise ValueError(
                f"Schedule logic error in {station_config['network_name']}: Clip shows are not currently supported as sequences"
            )

        # check if the sequence already exists

        existing = SequenceIO().get_sequence(station_config["network_name"], seq_name, seq_tag)

        if not existing:
            seq_start = 0
            seq_end = 1
            if "sequence_start" in slot:
                seq_start = slot["sequence_start"]
            if "sequence_end" in slot:
                seq_end = slot["sequence_end"]

            ns = NamedSequence(
                station_config["network_name"], seq_name, seq_tag, seq_start, seq_end, 0
            )

            file_list = MediaProcessor._rfind_media(f"{station_config['content_dir']}/{seq_tag}")
            ns.populate(file_list)
            SequenceIO().put_sequence(station_config["network_name"], ns)
            