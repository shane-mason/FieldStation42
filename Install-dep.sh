echo "Welcome to the auto install. Please stand by."
echo "Updating and upgrading packages to not get errors."
sudo apt update && sudo apt upgrade
echo "Upgrade finished with no errors."
echo "Installing Deps"
echo "Installing Git"
sudo apt install git
echo "Installing python"
sudo apt install python3
echo "Installing mpv"
sudo apt install mpv
echo "Installing python packages"
pip3 install moviepy
pip3 install python-mpv-jsonipc
echo "There is one last thing then you have to read the readme for more."
pip3 install virtualenv
echo "The deps are done. Read the readme for more."
