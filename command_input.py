import time
import board
import digitalio
import datetime
import serial
import os
import sys

# listens for input on 'button press' and then writes to channel socket file (player will pick it up.)
# uses circuit python

#button = digitalio.DigitalInOut(board.D4)
#button.direction = digitalio.Direction.INPUT
#button.pull = digitalio.Pull.UP

#while True:
#    if not button.value:
#        timestamp = datetime.datetime.now
#        with open("runtime/channel.socket") as fp:
#            fp.write(timestamp)

#        time.sleep(5)
#    else:
#        time.sleep(.05)



#uart = busio.UART(tx=board.GP0, rx=board.GP1)
uart = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=10)
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
