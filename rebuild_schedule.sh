#/usr/bin/bash


cd $(dirname $0)
. env/bin/activate

python3 fs42/station_42.py
