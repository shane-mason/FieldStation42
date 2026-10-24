import argparse
import glob
import json
import os
import secrets
import sys

MAIN_CONFIG = os.path.join("confs", "main_config.json")
FLUID_DB = os.path.join("runtime", "fs42_fluid.db")


def load_main_config(root):
    path = os.path.join(root, MAIN_CONFIG)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def has_key(conf):
    key = conf.get("api_key") if isinstance(conf, dict) else None
    return isinstance(key, str) and bool(key.strip())


def is_fresh_install(root):
    if os.path.exists(os.path.join(root, MAIN_CONFIG)):
        return False
    if os.path.exists(os.path.join(root, FLUID_DB)):
        return False
    return not glob.glob(os.path.join(root, "confs", "*.json"))


def write_key(root, conf):
    key = secrets.token_urlsafe(16)
    conf = dict(conf or {})
    conf["api_key"] = key
    os.makedirs(os.path.join(root, "confs"), exist_ok=True)
    with open(os.path.join(root, MAIN_CONFIG), "w") as f:
        json.dump(conf, f, indent=4)
        f.write("\n")
    return key


def ask_yes_no(prompt):
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def print_key(key):
    print(f"Your API key is: {key}")
    print(f"It is stored as \"api_key\" in {MAIN_CONFIG}.")
    print(f"Log in to the web console with it, or open http://<this-machine>:4242/login?api_key={key}")
    print("Scripts must send it too - see docs/API_SECURITY.md")


def setup(root=".", interactive=True):
    conf = load_main_config(root)

    if has_key(conf):
        print(f"API security is on - the key is \"api_key\" in {MAIN_CONFIG}.")
        return "already"

    if is_fresh_install(root):
        print("New install - turning on API security.")
        print_key(write_key(root, conf))
        return "generated"

    if not interactive or not sys.stdin.isatty():
        print(f"API security is off. To turn it on, add \"api_key\" to {MAIN_CONFIG} and restart,")
        print("or rerun the installer and answer yes. See docs/API_SECURITY.md")
        return "skipped"

    print("API security is off. When on, the web console asks for a key and scripts must send it.")
    print("See docs/API_SECURITY.md before turning it on if you have scripts that call FieldStation42.")
    if not ask_yes_no("Enable API security? [y/N] "):
        print(f"Leaving API security off. You can turn it on later by adding \"api_key\" to {MAIN_CONFIG}.")
        return "declined"

    if conf is not None:
        print(f"Note: {MAIN_CONFIG} has been rewritten - your settings are kept, but its formatting may change.")
    print_key(write_key(root, conf))
    print("Restart FieldStation42 for the key to take effect.")
    return "enabled"


def main():
    parser = argparse.ArgumentParser(description="Set up the FieldStation42 API key")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt")
    parser.add_argument("--root", default=".", help="FieldStation42 folder (default: current directory)")
    args = parser.parse_args()
    try:
        setup(args.root, interactive=not args.non_interactive)
    except (OSError, ValueError) as e:
        print(f"Could not set up the API key: {e}")
        print(f"You can add \"api_key\" to {MAIN_CONFIG} by hand - see docs/API_SECURITY.md")


if __name__ == "__main__":
    main()
