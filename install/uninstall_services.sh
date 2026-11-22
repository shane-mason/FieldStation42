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
echo -e "${YELLOW}Uninstalling FieldStation42 systemd user services${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

# Stop services
echo -e "${INFO} Stopping services..."
for service in fs42.service fs42-cable-box.service fs42-remote-controller.service fs42-osd.service; do
    if systemctl --user is-active --quiet "$service"; then
        systemctl --user stop "$service"
        echo -e "${CHECK} Stopped $service"
    else
        echo -e "${INFO} $service is not running"
    fi
done

# Disable services
echo ""
echo -e "${INFO} Disabling services..."
for service in fs42.service fs42-cable-box.service fs42-remote-controller.service fs42-osd.service; do
    if systemctl --user is-enabled --quiet "$service" 2>/dev/null; then
        systemctl --user disable "$service"
        echo -e "${CHECK} Disabled $service"
    else
        echo -e "${INFO} $service is not enabled"
    fi
done

# Remove service files
echo ""
echo -e "${INFO} Removing service files..."
for service in fs42.service fs42-cable-box.service fs42-remote-controller.service fs42-osd.service; do
    if [ -f "$SYSTEMD_USER_DIR/$service" ]; then
        rm "$SYSTEMD_USER_DIR/$service"
        echo -e "${CHECK} Removed $service"
    else
        echo -e "${INFO} $service file not found"
    fi
done

# Reload systemd daemon
echo ""
echo -e "${INFO} Reloading systemd daemon..."
systemctl --user daemon-reload
echo -e "${CHECK} Daemon reloaded"

# Note about lingering
echo ""
echo -e "${WARN} Note: User lingering was NOT disabled."
echo -e "       If you want to disable it, run: ${CYAN}loginctl disable-linger $USER${NC}"

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Services uninstalled successfully!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""
