#/usr/bin/bash


cd $(dirname $0)
. env/bin/activate

python3 station_42.py --rebuild_catalog