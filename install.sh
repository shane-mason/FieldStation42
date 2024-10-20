#! /usr/bin/bash

echo Installing Fieldstation 42
echo Finding python installation...
python=python3

if type "python3" > /dev/null; then
    echo "Found python3 - using that"
    python=python3
elif type "python" > /dev/null; then
    echo "Found python - using that"
    python=python
else
    echo ERROR :: Couldn\'t find python or python3 on the path
    echo Please install python and try again
    exit -1
fi

echo Moving forward with python :: $python
echo Creating python virtual environment

$python -m venv env

if [ -d env ]; then
  echo Virtual environment created - activating it now
  source env/bin/activate
else
  echo Virtual environment failed - check that your python venv is installed on your system
  echo Exiting with errors.
  exit -1
fi

echo Installing python modules
env/bin/pip3 install moviepy

env/bin/pip3 install python-mpv-jsonipc

echo Creating folders

if [ -d runtime ]; then
  echo Runtime folder exists - skipping
else
  echo Runtime folder doesn\'t exist, making now
  mkdir runtime
fi

echo Setting up runtime directory
cp docs/static.mp4 runtime
touch runtime/channel.socket

if [ -d catalog ]; then
  echo Catalog folder exists - skipping
else
  echo Catalog folder doesn\'t exist, making now
  mkdir catalog
fi
echo Installation is complete
echo You can find example configurations in confs/examples
