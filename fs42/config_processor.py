from datetime import datetime

from fs42 import timings


class ConfigurationError(Exception):
    pass


class ConfigProcessor:
    @staticmethod
    def preprocess(conf):
        # first, fill in templates
        processed = ConfigProcessor._process_templates(conf)
        processed = ConfigProcessor._process_strategy(processed)
        processed = ConfigProcessor._process_date_overrides(processed)
        return processed

    @staticmethod
    def _valid_date_key(date_key):
        # validate that this looks like either "Month Day" or "Month Day - Month Day"
        # raises ConfigurationError with helpful message on failure
        parts = [part.strip() for part in date_key.split(" - ")]

        if len(parts) not in (1, 2):
            raise ConfigurationError(
                f"Invalid date_overrides key '{date_key}'. "
                "Expected format 'Month Day' or 'Month Day - Month Day'."
            )

        for part in parts:
            try:
                datetime.strptime(part, "%B %d")
            except ValueError:
                raise ConfigurationError(
                    f"Invalid date '{part}' in date_overrides key '{date_key}'. "
                    "Ensure the day exists for the given month (e.g., April has 30 days)."
                )

        return True

    @staticmethod
    def _process_templates(conf):
        # first, see if there are templates
        if "day_templates" not in conf:
            return conf

        templates = conf["day_templates"]

        # now, go through each day:
        for day_key in timings.DAYS:
            if day_key not in conf:
                raise ConfigurationError(
                    f"{day_key} not found in config for {conf['network_name']} - requires an entry for each day of the week."
                )

            if isinstance(conf[day_key], str):
                # found a potential reference, so see if it exists
                ref_key = conf[day_key]
                if ref_key not in templates:
                    raise ConfigurationError(
                        f"Schedule for {conf['network_name']} references a template for {ref_key} on {day_key}, but that template doesn't exist."
                    )
                # then just inline it :)

                conf[day_key] = templates[ref_key]

        return conf

    @staticmethod
    def _process_date_overrides(conf):
        if "date_overrides" not in conf:
            return conf

        overrides = conf["date_overrides"]

        if not isinstance(overrides, dict):
            raise ConfigurationError(
                f"date_overrides for {conf['network_name']} must be an object mapping dates to slot definitions."
            )

        processed_overrides = {}

        for date_key, override_value in overrides.items():
            # validate date key (will raise ConfigurationError if invalid)
            ConfigProcessor._valid_date_key(date_key)

            if isinstance(override_value, str):
                template_key = override_value

                if "day_templates" not in conf or template_key not in conf["day_templates"]:
                    raise ConfigurationError(
                        f"date_overrides entry '{date_key}' for {conf['network_name']} references template '{template_key}', but that template doesn't exist."
                    )

                processed_overrides[date_key] = conf["day_templates"][template_key]

            elif isinstance(override_value, dict):
                processed_overrides[date_key] = override_value

            else:
                raise ConfigurationError(
                    f"date_overrides entry '{date_key}' for {conf['network_name']} must be either a day template reference or an object of hourly slots."
                )

        conf["date_overrides"] = processed_overrides
        return conf

    @staticmethod
    def _process_strategy(conf):
        if "slot_overrides" not in conf:
            return conf

        overrides = conf["slot_overrides"]
        overridable = [
            "start_bump",
            "end_bump",
            "bump_dir",
            "commercial_dir",
            "break_strategy",
            "sequence",
            "sequence_start",
            "sequence_end",
            "schedule_increment",
            "random_tags",
            "video_scramble_fx",
            "marathon",
        ]

        for day_key in timings.DAYS:
            for hour_key in list(conf[day_key]):
                if "overrides" in conf[day_key][hour_key]:

                    o_key = conf[day_key][hour_key]["overrides"]
                    if o_key not in conf["slot_overrides"]:
                        raise ConfigurationError(
                            f"Schedule for {conf['network_name']} on {day_key} at {hour_key} references a slot override {o_key} that doesn't exist."
                        )

                    or_def = overrides[o_key]

                    for to_override in or_def:
                        if to_override not in overridable:
                            raise ConfigurationError(
                                f"Schedule for {conf['network_name']} is trying to override {to_override} in {o_key}, but only the following can be overriden: {overridable}"
                            )

                        conf[day_key][hour_key][to_override] = or_def[to_override]

                    del conf[day_key][hour_key]["overrides"]

        return conf
