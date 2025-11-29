#! /usr/bin/bash

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Progress Indicators
CHECK="${GREEN}[✓]${NC}"
INFO="${BLUE}[→]${NC}"
WARN="${YELLOW}[!]${NC}"
ERROR="${RED}[✗]${NC}"

# Clear screen and show banner
clear
echo ""
echo -e "${CYAN}═════════════════════════════════════════════════════════════${NC}"
echo -e "${MAGENTA}    _____ _      _     _ ____  _        _   _             ${NC}"
echo -e "${MAGENTA}   |  ___(_) ___| | __| / ___|| |_ __ _| |_(_) ___  _ __  ${NC}"
echo -e "${MAGENTA}   | |_  | |/ _ \ |/ _\` \___ \| __/ _\` | __| |/ _ \| '_ \ ${NC}"
echo -e "${MAGENTA}   |  _| | |  __/ | (_| |___) | || (_| | |_| | (_) | | | |${NC}"
echo -e "${MAGENTA}   |_|   |_|\___|_|\__,_|____/ \__\__,_|\__|_|\___/|_| |_|${NC}"
echo ""
echo -e "${MAGENTA}                    _  _    ____                               ${NC}"
echo -e "${MAGENTA}                   | || |  |___ \                              ${NC}"
echo -e "${MAGENTA}                   | || |_   __) |                             ${NC}"
echo -e "${MAGENTA}                   |__   _| / __/                              ${NC}"
echo -e "${MAGENTA}                      |_|  |_____|                             ${NC}"
echo ""
echo -e "${CYAN}                     It's Up To You                         ${NC}"
echo -e "${CYAN}═════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}This installer will:${NC}"
echo -e "  • Install FieldStation42 dependencies"
echo -e "  • Set up a Python virtual environment"
echo -e "  • Create necessary runtime directories"
echo -e "  • Copy default media files"
echo ""
echo -e "${GREEN}Your existing configuration files will NOT be overwritten.${NC}"
echo ""
read -p "Press Enter to proceed (or Ctrl+C to cancel)... "
echo ""
echo -e "${BLUE}Starting installation...${NC}"
echo ""

echo -e "${INFO} Finding python installation..."
python=python3

if type "python3" > /dev/null; then
    echo -e "${CHECK} Found python3 - using that"
    python=python3
elif type "python" > /dev/null; then
    echo -e "${CHECK} Found python - using that"
    python=python
else
    echo -e "${ERROR} Couldn't find python or python3 on the path"
    echo -e "${ERROR} Please install python and try again"
    exit -1
fi

echo -e "${INFO} Moving forward with python :: ${GREEN}$python${NC}"
echo -e "${INFO} Creating python virtual environment..."

if [ -f /.dockerenv ]; then
  echo -e "${WARN} Running inside Docker — skipping venv setup."

else
  $python -m venv env
  # do your venv setup
  if [ -d env ]; then

    echo -e "${CHECK} Virtual environment created - activating it now"
    # Unix
    if [ -f env/Scripts/activate ]; then
      source env/Scripts/activate
    # Windows
    elif [ -f env/bin/activate ]; then
      source env/bin/activate
    else
      echo -e "${ERROR} Virtual environment does not contain activate script - this is an error"
      echo -e "${ERROR} Ensure that python3-venv is installed and run the installer again."
      exit -1
    fi
  else
    echo -e "${ERROR} Virtual environment failed - check that your python venv is installed on your system"
    echo -e "${ERROR} Exiting with errors."
    exit -1
  fi
fi


echo ""
echo -e "${INFO} Installing python modules..."
pip install -r install/requirements.in

echo ""
echo -e "${INFO} Creating folders..."

if [ -d runtime ]; then
  echo -e "${CHECK} Runtime folder exists - skipping"
else
  echo -e "${INFO} Runtime folder doesn't exist, making now"
  mkdir runtime
  echo -e "${CHECK} Runtime folder created"
fi

echo -e "${INFO} Setting up runtime directory..."

# Copy runtime files only if they don't exist
files_copied=0
for file in static.mp4 standby.png brb.png off_air_pattern.mp4 signoff.mp4; do
  if [ -f "runtime/$file" ]; then
    echo -e "${CHECK} $file already exists - skipping"
  else
    cp "docs/$file" runtime/
    echo -e "${CHECK} Copied $file"
    files_copied=$((files_copied + 1))
  fi
done

if [ $files_copied -eq 0 ]; then
  echo -e "${INFO} All runtime files already exist"
fi

if [ ! -f runtime/channel.socket ]; then
  touch runtime/channel.socket
  echo -e "${CHECK} Channel socket created"
else
  echo -e "${CHECK} Channel socket already exists - skipping"
fi

if [ -d catalog ]; then
  echo -e "${CHECK} Catalog folder exists - skipping"
else
  echo -e "${INFO} Catalog folder doesn't exist, making now"
  mkdir catalog
  echo -e "${CHECK} Catalog folder created"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Installation is complete!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${INFO} You can find example configurations in ${CYAN}confs/examples${NC}"
echo -e "${INFO} Visit the wiki for details ${CYAN}https://github.com/shane-mason/FieldStation42/wiki${NC}"
echo ""
echo -e "${INFO} To set up FieldStation42 as auto-starting systemd services:"
echo -e "       ${CYAN}bash install/install_services.sh${NC}"
echo ""
echo -e "${WARN} NOTE: If you want to use web type channels on Raspberry Pi Bookworm,"
echo -e "       you will also need to run:"
echo -e "       ${YELLOW}sudo bash install/web_reqs.sh${NC}"
echo ""
