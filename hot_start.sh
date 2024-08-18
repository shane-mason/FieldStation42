#/usr/bin/bash

cd ~/FieldStation42
. env/bin/activate

python3 field_player.py &
python3 aerial_listener.py &
