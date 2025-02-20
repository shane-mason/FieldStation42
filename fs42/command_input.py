import time
import datetime
import serial
import os
import sys
import json

uart = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=10)

def old_loop():
    while True:
        time.sleep(0.1)
        if (uart.in_waiting > 0):
            message = uart.readline()
            command = message.decode('ascii')
            print("Got Message: ", command)
            if command.startswith("change"):
                timestamp = datetime.datetime.now()
                with open("runtime/channel.socket", "w") as fp:
                    fp.write(str(timestamp))
            if command.startswith("exit"):
                os.system("pkill -9 -f field_player.py")
                os.system("killall mpv")
                sys.exit(-1)

            if command.startswith("halt"):
                os.system("pkill -9 -f field_player.py")
                os.system("killall mpv")
                os.system("sudo halt")
                sys.exit(-1)


def new_loop():
    last_stat = ""
    while True:
        time.sleep(0.1)
        if (uart.in_waiting > 0):
            message = uart.readline()
            command = message.decode('ascii')
            print("Got Message: ", command)
            try:
                as_json = json.loads(command)

                if as_json['channel'] == 99:
                    os.system("pkill -9 -f field_player.py")
                    os.system("killall mpv")
                    sys.exit(-1)
                elif as_json['channel'] == 98:
                    os.system("pkill -9 -f field_player.py")
                    os.system("killall mpv")
                    os.system("sudo halt")
                    sys.exit(-1)
                else:
                    with open("runtime/channel.socket", "w") as fp:
                        fp.write(command)
            except Exception as e:
                print("Error decoding message")
                print(e)
        else:
            with open("runtime/play_status.socket") as fp:
                as_str = fp.read()
                
                if as_str != last_stat:
                    print("Status changed:")
                    last_stat = as_str
                    as_str = as_str.rstrip()
                    print(as_str)
                    uart.write(f"{as_str}\n".encode('utf-8'))
                    uart.flush()

            

if __name__ == "__main__":
    new_loop()