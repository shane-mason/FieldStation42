# 📱 FieldStation42 Remote Controller

Control your FieldStation42 server with any IR remote using Flirc USB or customize keyboard mappings for direct control.

## 🚀 Quick Start with Flirc USB

**Flirc USB** lets you use any IR remote with your Raspberry Pi. It's the easiest way to get remote control working!

### 1. Set up Flirc USB
1. **Get Flirc**: Buy a [Flirc USB receiver](https://flirc.tv/) (~$20)
2. **Install Flirc software** on your computer:
   ```bash
   # Download from https://flirc.tv/more/flirc-usb
   # Or install via package manager
   sudo apt install flirc
   ```

3. **Program your remote** using the Flirc GUI:
   - Numbers **0-9** → Map to keyboard numbers `0-9`
   - **Home/Guide** → Map to `Home` key
   - **Volume Up** → Map to `Right Arrow` key  
   - **Volume Down** → Map to `Left Arrow` key
   - **Channel Up** → Map to `Up Arrow` key
   - **Channel Down** → Map to `Down Arrow` key
   - **Power/Stop** → Map to `End` key

4. **Plug Flirc** into your Raspberry Pi and you're done!

### 2. Run the Remote Controller
```bash
# Install dependencies
pip install evdev requests

# Run (needs sudo for input device access)
sudo python3 remote_controller.py
```

## ⚙️ Customize Key Mappings

Don't have Flirc? Want different keys? Easy! Just edit the `KEY_MAPPINGS` section at the top of `remote_controller.py`:

```python
KEY_MAPPINGS = {
    'show_guide': 'home',        # Show program guide
    'volume_up': 'right',        # Increase volume
    'volume_down': 'left',       # Decrease volume  
    'channel_up': 'up',          # Next channel
    'channel_down': 'down',      # Previous channel
    'power_stop': 'end',         # Stop player
    'exit': 'esc',               # Exit remote controller
}
```

### Example Customizations

**Use spacebar for power, letters for navigation:**
```python
KEY_MAPPINGS = {
    'show_guide': 'g',           # Press 'G' for guide
    'volume_up': 'pageup',       # Page Up for volume up
    'volume_down': 'pagedown',   # Page Down for volume down
    'channel_up': 'w',           # 'W' for channel up
    'channel_down': 's',         # 'S' for channel down
    'power_stop': 'space',       # Spacebar to stop
    'exit': 'q',                 # 'Q' to quit
}
```

**Use function keys:**
```python
KEY_MAPPINGS = {
    'show_guide': 'f1',          # F1 for guide
    'volume_up': 'f2',           # F2 for volume up
    'volume_down': 'f3',         # F3 for volume down
    'channel_up': 'f4',          # F4 for channel up
    'channel_down': 'f5',        # F5 for channel down  
    'power_stop': 'f12',         # F12 to stop
    'exit': 'esc',               # ESC to quit
}
```

### Available Key Names
- **Letters**: `a` through `z`
- **Function keys**: `f1` through `f12`
- **Arrows**: `up`, `down`, `left`, `right`
- **Navigation**: `home`, `end`, `pageup`, `pagedown`, `insert`, `delete`
- **Common**: `space`, `enter`, `tab`, `backspace`, `esc`
- **Modifiers**: `leftshift`, `rightshift`, `leftctrl`, `rightctrl`, `leftalt`, `rightalt`

## 🔧 Configuration

### Server Settings
Change the FieldStation42 server location:
```bash
# Environment variables
FS42_HOST=192.168.1.100 FS42_PORT=8080 sudo python3 remote_controller.py

# Or edit the script directly
FS42_HOST = '192.168.1.100'
FS42_PORT = '8080'
```

### Input Device Selection

By default, the remote controller automatically finds your Flirc device. If you have multiple input devices or want to use a specific keyboard, you can specify which one to use:

**Command-line options:**
```bash
# List all available input devices
sudo python3 remote_controller.py --list-devices

# Use a specific device path
sudo python3 remote_controller.py -d /dev/input/event3

# Use device by index (from --list-devices output)
sudo python3 remote_controller.py -d 0

# Use device by name pattern (finds first match)
sudo python3 remote_controller.py -d flirc
sudo python3 remote_controller.py -d keyboard
```

**Environment variable:**
```bash
# Set device persistently via environment variable
FS42_INPUT_DEVICE=keyboard sudo python3 remote_controller.py

# Combine with other settings
FS42_HOST=192.168.1.100 FS42_INPUT_DEVICE=1 sudo python3 remote_controller.py
```

**How device selection works:**
1. **Device path** (`/dev/input/event3`) - Uses exact device path
2. **Device index** (`0`, `1`, `2`) - Uses device at that position in the list
3. **Name pattern** (`flirc`, `keyboard`) - Finds first device containing that text
4. **Auto-detect** (default) - Automatically finds Flirc, or uses first available device

## 📺 Remote Functions

| Function | Default Key | Description |
|----------|-------------|-------------|
| **Numbers 0-9** | `0-9` | Channel selection (always works) |
| **Show Guide** | `Home` | Display program guide |
| **Volume Up** | `Right Arrow` | Increase volume by 5% |
| **Volume Down** | `Left Arrow` | Decrease volume by 5% |
| **Channel Up** | `Up Arrow` | Next channel |
| **Channel Down** | `Down Arrow` | Previous channel |
| **Power/Stop** | `End` | Stop the player |
| **Exit** | `Esc` | Exit remote controller |

### Channel Selection
- Press **1** → Wait 1 second → Switch to channel 1
- Press **1**, **2** → Wait 1 second → Switch to channel 12  
- Press **1**, **2**, **3** → Immediately switch to channel 123

## 🔧 Installation & Requirements

### Prerequisites
- **Raspberry Pi** (or any Linux system)
- **Python 3** with pip
- **FieldStation42** server running
- **Flirc USB** (recommended) or keyboard access

### Install Dependencies
```bash
pip install evdev requests
```

### Run the Controller
```bash
# Standard usage (may need sudo for input device access)
sudo python3 remote_controller.py

# Custom server location
FS42_HOST=192.168.1.50 sudo python3 remote_controller.py
```

## 🐛 Troubleshooting

### "Permission denied" Error
```bash
# Run with sudo to access input devices
sudo python3 remote_controller.py
```

### "No keyboard/remote devices found"
- Check that Flirc USB is plugged in
- Verify with: `ls /dev/input/event*`
- Try running with sudo
- Use `--list-devices` to see all available input devices

### Remote Not Responding
1. **Check Flirc programming**: Use Flirc GUI to verify key mappings
2. **Test device**: Run `evtest` to see if keys are detected
3. **Check server**: Verify FieldStation42 is running on correct host/port

### Custom Keys Not Working
- Check available keys: Look at the `get_key_name_from_code()` function
- Test key names: Use `evtest` to see the actual key names your device sends

## 🎯 Pro Tips

1. **Flirc Setup**: Use the Flirc GUI's "Full Keyboard" controller template for best results
2. **SSH Usage**: Perfect for headless Raspberry Pi setups via SSH
3. **Multiple Remotes**: Each family member can program their own remote buttons
4. **Key Testing**: Use `sudo evtest` to see what keys your device actually sends
5. **Background Running**: Use `screen` or `tmux` to run the controller in the background

---

**Happy channel surfing! 📺✨**