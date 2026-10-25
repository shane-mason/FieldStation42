# FieldStation42 systemd Services

FieldStation42 can run as systemd user services, which means:
- Automatically starts on login
- Runs in background (no terminal windows)
- Automatic restart on failure
- Centralized logging via systemd journal
- Easy management with systemctl commands

## Installation

**Important:** Only install systemd services after you have FieldStation42 configured and running stably. This is not part of the initial installation.

When ready, run:

```bash
bash install/install_services.sh
```

The installer will prompt you to select which services to enable:
- **Field Player** (fs42) - Core service, enabled by default
- **Cable Box** (fs42-cable-box) - Optional, for cable box interface
- **Remote Controller** (fs42-remote-controller) - Optional
- **OSD** (fs42-osd) - Optional, on-screen display overlay

Services are enabled but not started immediately. They will start automatically on next login, or you can start them manually.

## Managing Services

### Field Player (main service)

The field player is the core service that manages content playback. You'll restart this most often:

```bash
# Start
systemctl --user start fs42

# Stop
systemctl --user stop fs42

# Restart (most common)
systemctl --user restart fs42

# Check status
systemctl --user status fs42

# View logs
journalctl --user -u fs42 -f
```

### All Services

```bash
# Start all
systemctl --user start fs42-*

# Stop all
systemctl --user stop fs42-*

# Restart all
systemctl --user restart fs42-*

# Check status of all
systemctl --user status fs42-*

# View all logs
journalctl --user -u fs42-* -f
```

### Individual Services

- `fs42` - Field Player (main content playback)
- `fs42-cable-box` - Cable Box interface
- `fs42-remote-controller` - Remote Controller
- `fs42-osd` - On-Screen Display (waits 30s before starting)
- `fs42-standby` - Web console only, used while FieldStation42 is stopped from the Manage page

If `api_key` is set, the **Manage** page in the web console can also restart or stop all running `fs42*` services.

`fs42-standby` is installed but never enabled, and the installer doesn't ask about it. It runs only the web console, and the Manage page's **Stop** button starts it. It conflicts with the other FieldStation42 services except the remote controller, so starting it stops them, and starting `fs42` again stops it. The remote controller stays running so its power button can turn FieldStation42 back on. It isn't restarted at boot, so a stopped box comes back up playing.

## Uninstall

```bash
bash install/uninstall_services.sh
```
