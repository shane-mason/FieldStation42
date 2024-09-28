echo "Welcome to phrase 2 of the installer. Please wait."
echo "Cloning repostory."
git clone http://github.com/shane-mason/FieldStation42.git
echo "Creating catalog folder."
sudo mkdir catalog
cd catalog
echo "Creating abc catalog."
sudo mkdir abc_catalog
cd abc_catalog
echo "Creating bumps folder."
sudo mkdir bumps
echo "Creating cartoon folder."
sudo mkdir cartoon
echo "Creating commercial folder."
sudo mkdir commercials
echo "Creating daytime folder."
sudo mkdir daytime
echo "Creating late folder."
sudo mkdir late
echo "Creating late-late folder."
sudo mkdir late-late
echo "Creating morning folder."
sudo mkdir morning
echo "Creating primetime folder."
sudo mkdir primetime
echo "Creating sports folder."
sudo mkdir sports
echo "Creating bump folder."
sudo mkdir bump
cd ..
echo "Creating cbs catalog."
sudo mkdir cbs_catalog
cd cbs_catalog
sudo mkdir bumps
sudo mkdir cartoon
sudo mkdir commercials
sudo mkdir daytime
sudo mkdir late
sudo mkdir morning
sudo mkdir primetime
sudo mkdir sports
sudo mkdir bumps
cd ..
echo "Creating nbc catalog."
sudo mkdir nbc_catalog
cd nbc_catalog
sudo mkdir bumps
sudo mkdir cartoon
sudo mkdir commercials
sudo mkdir daytime
sudo mkdir late
sudo mkdir morning
sudo mkdir primetime
sudo mkdir sports
sudo mkdir bumps
cd ..
echo "Creating pbs catalog."
sudo mkdir pbs_catalog
cd pbs_catalog
sudo mkdir bumps
sudo mkdir cartoon
sudo mkdir commercials
sudo mkdir daytime
sudo mkdir late
sudo mkdir morning
sudo mkdir primetime
sudo mkdir sports
sudo mkdir bumps
cd ..
echo "Add your videos in the folders in the Catalog folders directory. The catalog folders have The station name then _catalog for example pbs_catalog"
echo "Continuing install."
cd ..
echo "Creating runtime folder."
sudo mkdir runtime
echo "Entering runtime folder"
cd runtime
echo "Creating abc folder."
sudo mkdir abc
echo "Creating nbc folder."
sudo mkdir nbc
echo "Creating cbs folder."
sudo mkdir cbs
echo "Creating pbs folder."
sudo mkdir pbs
