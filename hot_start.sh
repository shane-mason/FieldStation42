#/usr/bin/bash

cd ~/FieldStation42
. env/bin/activate

python3 field_player.py 1>/dev/null 2>/dev/null & disown
python3 aerial_listener.py 1>/dev/null 2>/dev/null & disown
