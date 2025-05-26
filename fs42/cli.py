import argparse
import subprocess
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from enum import auto, StrEnum

class EnvironmentType(StrEnum):
    DOCKER = auto()
    LOCAL = auto()

# Load .env file (if it exists)
load_dotenv()

SCRIPT_MAP = {
    "station_42": "station_42.py",
    "field_player": "field_player.py",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTAINER_NAME = "fieldstation42"

def main():
    parser = argparse.ArgumentParser(prog="fs42", description="Fieldstation 42 CLI")
    
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-d", "--docker", action="store_true", help="Force Docker mode")
    mode_group.add_argument("-l", "--local", action="store_true", help="Force Local mode")

    parser.add_argument("command", choices=SCRIPT_MAP.keys(), help="Which script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")

    parsed = parser.parse_args()

    script = SCRIPT_MAP[parsed.command]
    script_path = PROJECT_ROOT / script

    # Determine effective mode
    if parsed.docker:
        mode = EnvironmentType.DOCKER
    elif parsed.local:
        mode = EnvironmentType.LOCAL
    else:
        mode = EnvironmentType(os.getenv("FIELDSTATION_MODE", EnvironmentType.LOCAL))

    # Dispatch based on mode
    match mode:
        case EnvironmentType.DOCKER:
            run_in_docker(script, parsed.args)
        case EnvironmentType.LOCAL:
            run_locally(script_path, parsed.args)
        case _:
            raise ValueError

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
