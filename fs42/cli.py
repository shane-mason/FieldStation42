import argparse
import subprocess
import os
import sys
from pathlib import Path
from dotenv import load_dotenv, set_key, dotenv_values, find_dotenv
from enum import auto, StrEnum

class EnvironmentType(StrEnum):
    DOCKER = auto()
    LOCAL = auto()

load_dotenv()

SCRIPT_ALIASES = {
    "station_42": "station_42.py",
    "catalog": "station_42.py",

    "field_player": "field_player.py",
    "play": "field_player.py",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTAINER_NAME = "fieldstation42"

def main():
    parser = argparse.ArgumentParser(prog="fs42", description="Fieldstation 42 CLI")

    parser.add_argument(
        "--set_default_mode",
        choices=[e.value for e in EnvironmentType],
        help="Persistently set the default mode to 'docker' or 'local'."
    )

    early_args, remaining_args = parser.parse_known_args()

    if early_args.set_default_mode:
        update_env_default_mode(early_args.set_default_mode)
        print(f"[fs42] Default mode set to '{early_args.set_default_mode}'.")
        sys.exit(0)

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-d", "--docker", action="store_true", help="Force Docker mode")
    mode_group.add_argument("-l", "--local", action="store_true", help="Force Local mode")

    parser.add_argument("command", choices=SCRIPT_ALIASES.keys(), help="Which script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")

    parsed = parser.parse_args(remaining_args)

    script = SCRIPT_ALIASES[parsed.command]
    script_path = PROJECT_ROOT / script

    # Determine effective mode
    if parsed.docker:
        mode = EnvironmentType.DOCKER
    elif parsed.local:
        mode = EnvironmentType.LOCAL
    else:
        mode = EnvironmentType(os.getenv("FIELDSTATION_MODE", EnvironmentType.LOCAL))

    match mode:
        case EnvironmentType.DOCKER:
            run_in_docker(script, parsed.args)
        case EnvironmentType.LOCAL:
            run_locally(script_path, parsed.args)
        case _:
            raise ValueError



def update_env_default_mode(mode: str):
    env_path = find_dotenv(usecwd=True) or (PROJECT_ROOT / ".env")
    set_key(env_path, "FIELDSTATION_MODE", mode)

def run_locally(script_path, args):
    if not script_path.exists():
        print(f"[error] Script not found: {script_path}")
        sys.exit(1)

    command = [sys.executable, str(script_path)] + args
    subprocess.run(command)

def run_in_docker(script_name, args):
    print("[docker] Starting container...")
    subprocess.run(["docker", "compose", "up", "-d"], check=True)

    try:
        command = ["docker", "exec", "-it", CONTAINER_NAME, "python3", script_name] + args
        subprocess.run(command, check=True)
    finally:
        print("[docker] Shutting down container...")
        subprocess.run(["docker", "compose", "down"], check=True)


if __name__ == "__main__":
    main()
