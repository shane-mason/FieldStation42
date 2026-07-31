# Raspberry Pi kiosk viewer

The Pi is only a browser client. FieldStation42, FFmpeg, schedules, and media
remain on the Unraid server.

## Install

Use Raspberry Pi OS with Desktop, connect the Pi to the TV, and install
Chromium:

```bash
sudo apt update
sudo apt install chromium
sudo install -m 0755 raspberry-pi/fieldstation42-kiosk /usr/local/bin/
mkdir -p "$HOME/.config/autostart"
cp raspberry-pi/fieldstation42-kiosk.desktop "$HOME/.config/autostart/"
```

Edit `/usr/local/bin/fieldstation42-kiosk` and replace the example IP, or set
`FS42_WATCH_URL` in the desktop session to
`http://YOUR-UNRAID-IP:4242/watch`.

Disable blanking in **Raspberry Pi Configuration → Display → Screen
Blanking**, or run this once for the current desktop user:

```bash
mkdir -p "$HOME/.config/lxsession/LXDE-pi"
printf '%s\n' '@xset s off' '@xset -dpms' '@xset s noblank' \
  >> "$HOME/.config/lxsession/LXDE-pi/autostart"
```

Reboot. Chromium starts with the graphical desktop and restarts if it exits.
The watch page also retries when Unraid or the network is temporarily
unavailable.

## Controls

- Arrow keys: previous/next channel
- `M`: mute
- `F`: fullscreen
- `G`: program guide
- On-screen controls: channel, volume, mute, guide, and fullscreen

A wireless keyboard, media keyboard, or remote that emits these key presses
works without installing FieldStation42 on the Pi.
