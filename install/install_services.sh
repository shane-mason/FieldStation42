#!/usr/bin/bash

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Progress Indicators
CHECK="${GREEN}[✓]${NC}"
INFO="${BLUE}[→]${NC}"
WARN="${YELLOW}[!]${NC}"
ERROR="${RED}[✗]${NC}"

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Installing FieldStation42 systemd user services${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""


INSTALL_DIR=$(cd "$(dirname "$0")/.." && pwd)
echo -e "${INFO} FieldStation42 installation directory: ${GREEN}$INSTALL_DIR${NC}"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
if [ ! -d "$SYSTEMD_USER_DIR" ]; then
    echo -e "${INFO} Creating systemd user directory..."
    mkdir -p "$SYSTEMD_USER_DIR"
    echo -e "${CHECK} Created $SYSTEMD_USER_DIR"
else
    echo -e "${CHECK} Systemd user directory exists"
fi

# Process templates
echo ""
echo -e "${INFO} Installing service files..."
for template in "$INSTALL_DIR/install/systemd/"*.template; do
    if [ -f "$template" ]; then
        # Get the service filename (remove .template extension)
        service_name=$(basename "$template" .template)

        # Replace __INSTALL_DIR__ with actual path and write to systemd directory
        sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$template" > "$SYSTEMD_USER_DIR/$service_name"

        echo -e "${CHECK} Installed $service_name"
    fi
done

echo ""
echo -e "${INFO} Reloading systemd daemon..."
systemctl --user daemon-reload
echo -e "${CHECK} Daemon reloaded"


echo ""
echo -e "${INFO} Enabling services to start on next login..."
for service in fs42.service fs42-cable-box.service fs42-remote-controller.service fs42-osd.service; do
    systemctl --user enable "$service"
    echo -e "${CHECK} Enabled $service"
done

echo ""
echo -e "${INFO} Enabling user lingering (services will run without active login)..."
loginctl enable-linger $USER
echo -e "${CHECK} Lingering enabled for $USER"

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Services installed successfully!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${INFO} Services will start automatically on next login."
echo -e "${INFO} To start them now, run: ${CYAN}systemctl --user start fs42-*${NC}"
echo ""
echo -e "${INFO} Useful commands:"
echo -e "  ${CYAN}systemctl --user status fs42-*${NC}       - Check status of all services"
echo -e "  ${CYAN}systemctl --user stop fs42-*${NC}         - Stop all services"
echo -e "  ${CYAN}systemctl --user restart fs42-*${NC}      - Restart all services"
echo -e "  ${CYAN}journalctl --user -u fs42-* -f${NC}       - View logs for all services"
echo ""
