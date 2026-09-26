# FieldStation42 Cable Box Script for Orange Pi Zero 3

## Overview

This is an alternative implementation of the FieldStation42 cable box script for the **Orange Pi Zero 3** running **Armbian**.

Unlike the Raspberry Pi implementation (`cable_box.py`), this version uses **libgpiod v1** to access GPIO pins through the Linux GPIO character device interface.

This script was tested using:

* Orange Pi Zero 3
* Armbian (Linux 6.6.x)
* Python 3
* libgpiod v1 Python bindings (`gpiod < 2`)

---

# Hardware

The current implementation assumes three physical push buttons:

| Function               | GPIO Pin | GPIO Line |
| ---------------------- | -------- | --------: |
| Restart FieldStation42 | PH2      |       226 |
| Channel Up             | PC11     |        75 |
| Channel Down           | PC15     |        79 |

The buttons are configured as active-low.

Current prototype hardware uses a breadboard.

---

# Prerequisites

Install the required system packages:

```bash
sudo apt update
sudo apt install gpiod python3-pip
```

Install the Python bindings for **libgpiod v1**:

```bash
pip3 install "gpiod<2"
```

> **Note**
>
> This script was written against the libgpiod v1 API.
>
> libgpiod v2 introduced API changes and is **not compatible** with this script.

---

# GPIO Access

Your user must have permission to access `/dev/gpiochip*`.

On Armbian this is typically done by adding the user to the `gpio` group.

Example:

```bash
sudo usermod -aG gpio $USER
```

Log out and log back in (or reboot) afterwards.

To verify GPIO access:

```bash
gpiodetect
```

Example output:

```text
gpiochip0 [platform] (27 lines)
```

To inspect GPIO line assignments:

```bash
gpioinfo
```

The script uses:

```
PH2  -> line 226
PC11 -> line 75
PC15 -> line 79
```

The `gpioinfo` utility is part of **libgpiod** and can identify GPIO chips by number, name, or device path (for example `/dev/gpiochip0`).

---

# Installing the Script

Copy

```
cable_box_opizero3-gpiodv1.py
```

into the same directory as the original cable box script.

---

# Updating the Service

The default service is configured for Raspberry Pi:

```
cable_box.py
```

Edit the user service:

```bash
nano ~/.config/systemd/user/fs42-cable-box.service
```

Replace the Raspberry Pi script:

```text
ExecStart=/usr/bin/python3 .../cable_box.py
```

with

```text
ExecStart=/usr/bin/python3 .../cable_box_opizero3-gpiodv1.py
```

Reload systemd:

```bash
systemctl --user daemon-reload
systemctl --user restart fs42-cable-box
```

---

# Current Button Mapping

| Button       | Action                                   |
| ------------ | ---------------------------------------- |
| Channel Up   | Moves to the next channel                |
| Channel Down | Moves to the previous channel            |
| Restart      | Restarts the FieldStation42 user service |

The restart button is intended as a recovery button if the frontend becomes unresponsive.

---

# Notes

* This implementation intentionally mirrors the behaviour of the Raspberry Pi cable box script while replacing the GPIO backend with libgpiod.
* GPIO numbering follows the Orange Pi Zero 3 pin assignments reported by `gpioinfo`.
* This implementation currently supports physical buttons only.
* IR receiver support is not yet implemented.

---

# Acknowledgements

Based on the original Raspberry Pi cable box implementation included with FieldStation42.

Orange Pi Zero 3 support implemented using the Linux GPIO character device (`libgpiod`).
