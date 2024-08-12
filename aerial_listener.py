import time
import board
import digitalio
import datetime

# listens for input on 'button press' and then writes to channel socket file (player will pick it up.)
# uses circuit python

button = digitalio.DigitalInOut(board.D4)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP

while True:
    if not button.value:
        timestamp = datetime.datetime.now
        with open("runtime/channel.socket") as fp:
            fp.write(timestamp)

        time.sleep(5)
    else:
        time.sleep(.05)

