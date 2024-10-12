#/usr/bin/bash

cd ~/FieldStation42
. env/bin/activate

python3 field_player.py 1>/dev/null 2>/dev/null & disown
python3 command_input.py 1>/dev/null 2>/dev/null & disown
