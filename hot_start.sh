#/usr/bin/bash


cd $(dirname $0)
. env/bin/activate

python3 field_player.py 1>/dev/null 2>/dev/null & disown
python3 fs42/command_input.py 1>/dev/null 2>/dev/null & disown
