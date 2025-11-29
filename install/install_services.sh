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

# Prompt for each service
echo ""
echo -e "${CYAN}Select which services to enable:${NC}"
echo ""

SERVICES_TO_ENABLE=()

# Field Player
echo -e "${BLUE}Field Player${NC} - Main content playback service (core functionality)"
read -p "Enable fs42.service? (Y/n): " enable_fp
if [[ ! "$enable_fp" =~ ^[Nn]$ ]]; then
    SERVICES_TO_ENABLE+=("fs42.service")
fi

# Cable Box
echo ""
echo -e "${BLUE}Cable Box${NC} - Cable box interface"
read -p "Enable fs42-cable-box.service? (y/N): " enable_cb
if [[ "$enable_cb" =~ ^[Yy]$ ]]; then
    SERVICES_TO_ENABLE+=("fs42-cable-box.service")
fi

# Remote Controller
echo ""
echo -e "${BLUE}Remote Controller${NC} - Remote controller interface"
read -p "Enable fs42-remote-controller.service? (y/N): " enable_rc
if [[ "$enable_rc" =~ ^[Yy]$ ]]; then
    SERVICES_TO_ENABLE+=("fs42-remote-controller.service")
fi

# OSD
echo ""
echo -e "${BLUE}On-Screen Display${NC} - Visual overlay (starts 30s after login)"
read -p "Enable fs42-osd.service? (y/N): " enable_osd
if [[ "$enable_osd" =~ ^[Yy]$ ]]; then
    SERVICES_TO_ENABLE+=("fs42-osd.service")
fi

# Enable selected services
if [ ${#SERVICES_TO_ENABLE[@]} -eq 0 ]; then
    echo ""
    echo -e "${WARN} No services selected for installation."
    echo -e "${INFO} You can run this script again later to install services."
    exit 0
fi

echo ""
echo -e "${INFO} Enabling services to start on next login..."
for service in "${SERVICES_TO_ENABLE[@]}"; do
    systemctl --user enable "$service"
    echo -e "${CHECK} Enabled $service"
done

# Only enable lingering if at least one service was enabled
echo ""
echo -e "${INFO} Enabling user lingering (services will run without active login)..."
loginctl enable-linger $USER
echo -e "${CHECK} Lingering enabled for $USER"

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Services installed successfully!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${INFO} Enabled services will start automatically on next login."
echo -e "${INFO} To start them now, run: ${CYAN}systemctl --user start <service-name>${NC}"
echo ""
echo -e "${INFO} Useful commands:"
echo -e "  ${CYAN}systemctl --user status fs42*${NC}        - Check status of enabled services"
echo -e "  ${CYAN}systemctl --user stop <service>${NC}      - Stop a specific service"
echo -e "  ${CYAN}systemctl --user restart <service>${NC}   - Restart a specific service"
echo -e "  ${CYAN}journalctl --user -u <service> -f${NC}    - View logs for a service"
echo ""
