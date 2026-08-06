import subprocess
import shlex
import time

class CommandExecutor:
    def __init__(self, command_str):
        self.command = command_str
        self.process = None

    def start(self):
        try:
            # Safely split command with spaces/quotes
            args = shlex.split(self.command)
            self.process = subprocess.Popen(args)
        except Exception as e:
            raise RuntimeError(f"Failed to start command: {e}")

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

    def get_status(self):
        if self.process is None:
            return "stopped"
        elif self.process.poll() is not None:
            return "completed"
        else:
            return "running"

def execute_command(channel_conf, input_check_fn):
    process = CommandExecutor(channel_conf["command"])
    process.start()
    keep_going = True
    while keep_going:
        time.sleep(0.05)
        response = input_check_fn()
        if response:
            print("Executable got shutdown command")
            keep_going = False
            process.stop()
            return response
        elif process.get_status() != "running":
            print("Executable not running")
            keep_going = False
