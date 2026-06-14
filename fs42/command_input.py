import time
import datetime
import serial
import os
import sys
import json
import subprocess

uart = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=10)


def old_loop():
    while True:
        time.sleep(0.1)
        if uart.in_waiting > 0:
            message = uart.readline()
            command = message.decode("ascii")
            print("Got Message: ", command)
            if command.startswith("change"):
                timestamp = datetime.datetime.now()
                with open("runtime/channel.socket", "w") as fp:
                    fp.write(str(timestamp))
            if command.startswith("exit"):
                subprocess.run(["pkill", "-9", "-f", "field_player.py"])
                subprocess.run(["killall", "mpv"])
                sys.exit(-1)

            if command.startswith("halt"):
                subprocess.run(["pkill", "-9", "-f", "field_player.py"])
                subprocess.run(["killall", "mpv"])
                subprocess.run(["sudo", "halt"])
                sys.exit(-1)


def new_loop():
    last_stat = ""
    while True:
        time.sleep(0.1)
        if uart.in_waiting > 0:
            try:
                message = uart.readline()
                command = message.decode("ascii")
                print("Got Message: ", command)
                as_json = json.loads(command)

                channel = as_json.get("channel")
                if channel == 99:
                    subprocess.run(["pkill", "-9", "-f", "field_player.py"])
                    subprocess.run(["killall", "mpv"])
                    sys.exit(-1)
                elif channel == 98:
                    subprocess.run(["pkill", "-9", "-f", "field_player.py"])
                    subprocess.run(["killall", "mpv"])
                    subprocess.run(["sudo", "halt"])
                    sys.exit(-1)
                elif isinstance(channel, int) and 0 <= channel <= 97:
                    with open("runtime/channel.socket", "w") as fp:
                        fp.write(str(channel))
            except Exception as e:
                print("Error decoding message")
                print(e)
        else:
            with open("runtime/play_status.socket") as fp:
                as_str = fp.read()

                if as_str != last_stat:
                    print("Status changed:")
                    last_stat = as_str
                    stat = json.loads(as_str)
                    uart.write(f"{stat['channel_number']}\n".encode("utf-8"))
                    # uart.flush()


if __name__ == "__main__":
    new_loop()
