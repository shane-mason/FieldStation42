import time
import board
import digitalio
import datetime

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
uart = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=10)
while True:
    time.sleep(0.01)
    if (uart.any() > 0):
        message = uart.read()
        command = message.decode('ascii')
        print("Got Message: ", command)
