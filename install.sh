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

if [ -f /.dockerenv ]; then
  echo "Running inside Docker — skipping venv setup."

else
  $python -m venv env
  # do your venv setup
  if [ -d env ]; then

    echo Virtual environment created - activating it now
    # Unix
    if [ -f env/Scripts/activate ]; then
      source env/Scripts/activate
    # Windows
    elif [ -f env/bin/activate ]; then
      source env/bin/activate
    else
      echo Virtual environment does not contain activate script - this is an error
      echo Ensure that python3-venv is installed and run the installer again.
      exit -1
    fi
  else
    echo Virtual environment failed - check that your python venv is installed on your system
    echo Exiting with errors.
    exit -1
  fi
fi


echo Installing python modules
pip install -r install/requirements.txt

echo Creating folders

if [ -d runtime ]; then
  echo Runtime folder exists - skipping
else
  echo Runtime folder doesn\'t exist, making now
  mkdir runtime
fi

echo Setting up runtime directory
cp docs/static.mp4 runtime
cp docs/standby.png runtime
cp docs/brb.png runtime
cp docs/off_air_pattern.mp4 runtime
cp docs/signoff.mp4 runtime

touch runtime/channel.socket

if [ -d catalog ]; then
  echo Catalog folder exists - skipping
else
  echo Catalog folder doesn\'t exist, making now
  mkdir catalog
fi
echo Installation is complete
echo You can find example configurations in confs/examples
