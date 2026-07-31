#!/usr/bin/env python3
"""Read-only validation for a FieldStation42 configuration directory."""

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ModuleNotFoundError:  # Unraid host validation fallback; image has jsonschema.
    jsonschema = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("confs", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("fs42/station_config_schema.json"))
    parser.add_argument("--find-network")
    args = parser.parse_args()

    if not args.confs.is_dir():
        print(f"Configuration directory does not exist: {args.confs}", file=sys.stderr)
        return 2

    try:
        schema = json.loads(args.schema.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load station schema: {exc}", file=sys.stderr)
        return 2

    station_count = 0
    matches = []
    errors = []
    for path in sorted(args.confs.glob("*.json")):
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        if path.name == "main_config.json":
            if not isinstance(document, dict):
                errors.append(f"{path.name}: expected a JSON object")
            continue
        if jsonschema is not None:
            try:
                jsonschema.validate(document, schema)
            except jsonschema.ValidationError as exc:
                errors.append(f"{path.name}: {exc.message}")
                continue
        else:
            station_conf = document.get("station_conf")
            if not isinstance(station_conf, dict):
                errors.append(f"{path.name}: missing station_conf object")
                continue
            if not isinstance(station_conf.get("network_name"), str):
                errors.append(f"{path.name}: missing network_name")
                continue
            if not isinstance(station_conf.get("channel_number"), int):
                errors.append(f"{path.name}: missing integer channel_number")
                continue
        station_count += 1
        network_name = document.get("station_conf", {}).get("network_name")
        if args.find_network and network_name == args.find_network:
            matches.append(path.name)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.find_network:
        print("\n".join(matches))
        return 0 if matches else 3
    if station_count == 0:
        print("No valid station configuration files were found.", file=sys.stderr)
        return 1
    print(f"Validated {station_count} station configuration file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
