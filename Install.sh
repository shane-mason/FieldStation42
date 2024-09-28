echo "Welcome to the auto install. Please stand by."
echo "Updating and upgrading packages to not get errors."
sudo apt update && sudo apt upgrade
echo "Upgrade finished with no errors."
echo "Installing Deps"
echo "Installing Git"
sudo apt install git
echo "Installing python"
sudo apt install python
echo "Installing mpv"
sudo apt install mpv
echo "Installing python packages"
pip3 install moviepy
