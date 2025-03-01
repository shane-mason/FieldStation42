from machine import Pin, UART
import json
import tm1637

tm = tm1637.TM1637(clk=Pin(1), dio=Pin(0), brightness=0)    
    
from keypad import Keypad
import time

# Define GPIO pins for rows
row_pins = [Pin(3),Pin(8),Pin(7),Pin(5)]
#row_pins = [Pin(),Pin(),Pin(),Pin()]

# Define GPIO pins for columns
column_pins = [Pin(9),Pin(2),Pin(6)]
#column_pins = [Pin(4),Pin(2),Pin()]


# Define keypad layout
keys = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['down', '0', 'up']]

keypad = Keypad(row_pins, column_pins, keys)

tm.show("FS42")

#setup uart
uart = UART(1)

uart.init(9600, tx=Pin(20), rx=Pin(21))

def send_command(command, channel=-1):
    as_obj = {'command' : command, 'channel': channel}
    as_str = json.dumps(as_obj)
    print(f"Sending command: {as_str}")
    uart.write(f"{as_str}\n")
    
def event_loop():
    
    last_pressed = ""
    in_selection = False
    last_selection_tick = -1
    channel_num = 0 
    while True:
        key_pressed = keypad.read_keypad()
        
        if key_pressed:
            tm.show(f"    ")
            last_selection_tick = time.ticks_ms()
            in_selection = True
            
            as_num = None
            print("Key pressed:", key_pressed)
            
            if key_pressed == "up":
                send_command("up")
                channel_num += 1
                tm.show(f"----")
                in_selection = False
            elif key_pressed == "down":
                if(channel_num > 0):
                    send_command("down")
                    channel_num -= 1
                    tm.show(f"----")
                in_selection = False
            else:                                    
                try:
                    as_num = int(last_pressed+key_pressed)
                    last_pressed = key_pressed
                    tm.show(f"  {as_num:02d}")
                except:
                    pass
            
            
            time.sleep(0.3)

            
        # see if we need to reset selection or apply it
        if in_selection:
            if time.ticks_diff( time.ticks_ms(), last_selection_tick) > 1500:
                print(f"Applying selection CH{as_num:02d}")
                tm.show(f"CH{as_num:02d}")
                last_selection_tick = -1
                in_selection = False
                last_pressed = ""
                channel_num = as_num
                send_command("direct", channel_num)
            
        
        time.sleep(0.1)
        
        while uart.any():
            print("Got message")
            print(uart.any())
            as_str = uart.readline()
            as_str = as_str.decode('ascii')
            as_str = as_str.rstrip()
            print(as_str)

            try:
                channel_num = int(as_str)
                if channel_num >= 0:
                    tm.show(f"CH{channel_num:02d}")
                    print("Set channel: ", channel_num)
                else:
                    tm.show("FS42")
            except:
                tm.show("FS42")

event_loop()

