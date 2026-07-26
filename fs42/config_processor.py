import copy
from datetime import datetime

from fs42 import timings


class ConfigurationError(Exception):
    pass


class ConfigProcessor:
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

    @staticmethod
    def preprocess(conf):
        # first, fill in templates
        processed = ConfigProcessor._process_templates(conf)
        processed = ConfigProcessor._process_strategy(processed)
        processed = ConfigProcessor._process_date_overrides(processed)
        processed = ConfigProcessor._process_week_overrides(processed)
        return processed

    @staticmethod
    def _expand_slot_overrides(slot, slot_override_defs, network_name, where):
        if not isinstance(slot, dict):
            raise ConfigurationError(f"Slot {where} for {network_name} must be a slot object.")

        if "overrides" not in slot:
            return slot

        slot = dict(slot)
        o_key = slot["overrides"]

        if o_key not in slot_override_defs:
            raise ConfigurationError(
                f"Slot {where} for {network_name} references a slot override '{o_key}' that doesn't exist."
            )

        or_def = slot_override_defs[o_key]
        for to_override in or_def:
            if to_override not in ConfigProcessor.overridable:
                raise ConfigurationError(
                    f"Slot {where} for {network_name} tries to override '{to_override}' in '{o_key}', "
                    f"but only the following can be overridden: {ConfigProcessor.overridable}"
                )
            slot[to_override] = or_def[to_override]

        del slot["overrides"]
        return slot

    @staticmethod
    def _valid_date_key(date_key, section="date_overrides"):
        # validate that this looks like either "Month Day" or "Month Day - Month Day"
        # raises ConfigurationError with helpful message on failure
        parts = [part.strip() for part in date_key.split(" - ")]

        if len(parts) not in (1, 2):
            raise ConfigurationError(
                f"Invalid {section} key '{date_key}'. "
                "Expected format 'Month Day' or 'Month Day - Month Day'."
            )

        for part in parts:
            try:
                datetime.strptime(part, "%B %d")
            except ValueError:
                raise ConfigurationError(
                    f"Invalid date '{part}' in {section} key '{date_key}'. "
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
                # then just inline it :) - copied, so later processing doesn't
                # rewrite the shared template and leak into everything else using it
                conf[day_key] = copy.deepcopy(templates[ref_key])

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

                override_value = copy.deepcopy(conf["day_templates"][template_key])

            elif not isinstance(override_value, dict):
                raise ConfigurationError(
                    f"date_overrides entry '{date_key}' for {conf['network_name']} must be either a day template reference or an object of hourly slots."
                )

            processed_overrides[date_key] = {
                hour_key: ConfigProcessor._expand_slot_overrides(
                    slot,
                    conf.get("slot_overrides", {}),
                    conf["network_name"],
                    f"in date_overrides '{date_key}' at hour {hour_key}",
                )
                for hour_key, slot in override_value.items()
            }

        conf["date_overrides"] = processed_overrides
        return conf

    @staticmethod
    def _process_week_overrides(conf):
        if "week_overrides" not in conf:
            return conf

        overrides = conf["week_overrides"]

        if not isinstance(overrides, dict):
            raise ConfigurationError(
                f"week_overrides for {conf['network_name']} must be an object mapping date ranges to week schedules."
            )

        templates = conf.get("day_templates", {})
        slot_override_defs = conf.get("slot_overrides", {})

        processed_overrides = {}

        for date_key, week_schedule in overrides.items():
            ConfigProcessor._valid_date_key(date_key, section="week_overrides")

            if not isinstance(week_schedule, dict):
                raise ConfigurationError(
                    f"week_overrides entry '{date_key}' for {conf['network_name']} must be an object with day keys."
                )

            # catch typo'd/capitalized day names rather than silently dropping them
            for present_key in week_schedule:
                if present_key not in timings.DAYS:
                    raise ConfigurationError(
                        f"week_overrides entry '{date_key}' for {conf['network_name']} has unknown day key "
                        f"'{present_key}' - expected one of: {timings.DAYS}"
                    )

            processed_week = {}
            for day_key in timings.DAYS:
                if day_key not in week_schedule:
                    continue

                day_val = week_schedule[day_key]

                if isinstance(day_val, str):
                    if day_val not in templates:
                        raise ConfigurationError(
                            f"week_overrides entry '{date_key}' on {day_key} for {conf['network_name']} "
                            f"references template '{day_val}', but that template doesn't exist."
                        )
                    day_val = templates[day_val]
                elif not isinstance(day_val, dict):
                    raise ConfigurationError(
                        f"week_overrides entry '{date_key}' on {day_key} for {conf['network_name']} "
                        "must be a day template reference or an object of hourly slots."
                    )

                processed_week[day_key] = {
                    hour_key: ConfigProcessor._expand_slot_overrides(
                        slot,
                        slot_override_defs,
                        conf["network_name"],
                        f"in week_overrides '{date_key}' on {day_key} at hour {hour_key}",
                    )
                    for hour_key, slot in day_val.items()
                }

            processed_overrides[date_key] = processed_week

        conf["week_overrides"] = processed_overrides
        return conf

    @staticmethod
    def _process_strategy(conf):
        if "slot_overrides" not in conf:
            return conf

        overrides = conf["slot_overrides"]

        for day_key in timings.DAYS:
            for hour_key in list(conf[day_key]):
                conf[day_key][hour_key] = ConfigProcessor._expand_slot_overrides(
                    conf[day_key][hour_key],
                    overrides,
                    conf["network_name"],
                    f"on {day_key} at hour {hour_key}",
                )

        return conf
